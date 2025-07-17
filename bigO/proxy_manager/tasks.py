import datetime
import ipaddress
import re
from datetime import timedelta
from zoneinfo import ZoneInfo

import influxdb_client
import sentry_sdk

from config.celery_app import app
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from . import models


@app.task
def sync_usage(regulate_seconds: int = 1 * 60 * 60):
    if not getattr(settings, "INFLUX_URL", False):
        return "no INFLUX_URL"
    # todo transaction.atomic(using="main") and select_for_update() had bug
    count = 0
    subscriptionperiod_qs = (
        models.SubscriptionPeriod.objects.using("main")
        .filter(
            Q(last_usage_at__gt=F("last_flow_sync_at") + timedelta(minutes=1))
            | Q(last_usage_at__isnull=False, last_flow_sync_at__isnull=True)
        )
        .order_by("last_flow_sync_at")[:10]
    )
    if not subscriptionperiod_qs.exists():
        return "nothing to do"
    for subscriptionperiod in subscriptionperiod_qs:
        now = timezone.now()
        if subscriptionperiod.flow_point_at is None:
            subscriptionperiod.flow_point_at = now - timedelta(seconds=regulate_seconds)
        query = f"""
from(bucket: "{settings.INFLUX_BUCKET}")
|> range(start: {subscriptionperiod.flow_point_at.strftime('%Y-%m-%dT%H:%M:%SZ')})
|> filter(fn: (r) => r["_measurement"] == "xray_usage")
|> filter(fn: (r) => r["_field"] == "dl_bytes" or r["_field"] == "up_bytes")
|> filter(fn: (r) => r["usage_type"] == "user")
|> filter(fn: (r) => r["period_id"] == "{subscriptionperiod.id}")
|> group(columns: ["_field"])  // group by _field to sum separately
|> sum()
"""
        df = (
            influxdb_client.InfluxDBClient(
                url=settings.INFLUX_URL, token=settings.INFLUX_TOKEN, org=settings.INFLUX_ORG
            )
            .query_api()
            .query_data_frame(query)
        )
        if df.empty:
            sentry_sdk.capture_message("did data not received by influx yet?")
            continue
        try:
            new_flow_download_bytes = df[df["_field"] == "dl_bytes"].iloc[0].to_dict()["_value"]
        except IndexError:
            new_flow_download_bytes = 0
        try:
            new_flow_upload_bytes = df[df["_field"] == "up_bytes"].iloc[0].to_dict()["_value"]
        except IndexError:
            new_flow_upload_bytes = 0
        if new_flow_download_bytes == 0 and new_flow_upload_bytes == 0:
            continue

        old_flow_download_bytes = subscriptionperiod.flow_download_bytes
        download_flow_diff = new_flow_download_bytes - old_flow_download_bytes
        subscriptionperiod.flow_download_bytes = new_flow_download_bytes
        subscriptionperiod.current_download_bytes += download_flow_diff

        old_flow_upload_bytes = subscriptionperiod.flow_upload_bytes
        upload_flow_diff = new_flow_upload_bytes - old_flow_upload_bytes
        subscriptionperiod.flow_upload_bytes = new_flow_upload_bytes
        subscriptionperiod.current_upload_bytes += upload_flow_diff

        subscriptionperiod.last_flow_sync_at = timezone.now()
        subscriptionperiod.save()
        count += 1
    return f"{count} processed"


@app.task
def forward_flow_point(flow_point_delta_seconds: int = 5 * 24 * 60 * 60):
    if not getattr(settings, "INFLUX_URL", False):
        return "no INFLUX_URL"
    flow_point_delta = timedelta(seconds=flow_point_delta_seconds)
    now = timezone.now()
    new_flow_point = now - flow_point_delta
    with transaction.atomic(using="main"):
        subscriptionperiod_qs = (
            models.SubscriptionPeriod.objects.filter(flow_point_at__lt=new_flow_point)
            .order_by("flow_point_at")[:10]
            .select_for_update()
        )
        if not subscriptionperiod_qs.exists():
            return "nothing to do"
        for subscriptionperiod in subscriptionperiod_qs:
            query = f"""
from(bucket: "{settings.INFLUX_BUCKET}")
|> range(start: {subscriptionperiod.flow_point_at.strftime('%Y-%m-%dT%H:%M:%SZ')}, stop: {new_flow_point.strftime('%Y-%m-%dT%H:%M:%SZ')})
|> filter(fn: (r) => r["_measurement"] == "xray_usage")
|> filter(fn: (r) => r["_field"] == "dl_bytes" or r["_field"] == "up_bytes")
|> filter(fn: (r) => r["usage_type"] == "user")
|> filter(fn: (r) => r["period_id"] == "{subscriptionperiod.id}")
|> group(columns: ["_field"])  // group by _field to sum separately
|> sum()
"""
            df = (
                influxdb_client.InfluxDBClient(
                    url=settings.INFLUX_URL, token=settings.INFLUX_TOKEN, org=settings.INFLUX_ORG
                )
                .query_api()
                .query_data_frame(query=query)
            )
            if not df.empty:
                between_download_bytes = df[df["_field"] == "dl_bytes"].iloc[0].to_dict()["_value"]
                between_upload_bytes = df[df["_field"] == "up_bytes"].iloc[0].to_dict()["_value"]

                new_flow_download_bytes = subscriptionperiod.flow_download_bytes - between_download_bytes
                if new_flow_download_bytes < 0:
                    sentry_sdk.capture_message(
                        f"negative for {subscriptionperiod=} flow_download_bytes is {new_flow_download_bytes / 1000} MB"
                    )
                    subscriptionperiod.current_download_bytes += abs(new_flow_download_bytes)
                    new_flow_download_bytes = 0
                subscriptionperiod.flow_download_bytes = new_flow_download_bytes

                new_flow_upload_bytes = subscriptionperiod.flow_upload_bytes - between_upload_bytes
                if new_flow_upload_bytes < 0:
                    subscriptionperiod.current_upload_bytes += abs(new_flow_upload_bytes)
                    new_flow_upload_bytes = 0
                subscriptionperiod.flow_upload_bytes = new_flow_upload_bytes

            subscriptionperiod.flow_point_at = new_flow_point
            subscriptionperiod.save()

@app.task
def process_xray_access_log(access_log_lines: str):
    pattern = r"""
                (?P<date>\d{4}\/\d{2}\/\d{2})[ ](?P<time>\d{2}:\d{2}:\d{2})
                .*?from\s+
                (?P<ip>(?:(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}|\d{1,3}(?:\.\d{1,3}){3})):\d+
                .*[ ](?P<protocol>\w+):(?P<domain>[^:\s]+):(?P<port>\d+)
                \s+\[(?P<inbound_tag_name>[^\]]+?)\s+->\s+(?P<outbound_tag_name>[^\]]+)\]
                .*?email:[ ]period(?P<period_id>\d+)\.profile(?P<profile_id>\d+)@love\.com
                """
    subscriptionperiodaccess_obj_list = []
    for line in access_log_lines.splitlines():
        match_res = re.search(pattern, line, re.VERBOSE)
        if len(match_res.groups()) != 10:
            print("No match.")
            continue
        time_ = match_res.group("time")
        date_ = match_res.group("date")
        datetime_ = datetime.datetime.strptime(f"{date_} {time_}", "%Y/%m/%d %H:%M:%S")
        datetime_ = datetime_.replace(tzinfo=ZoneInfo("UTC"))
        ip = ipaddress.ip_interface(match_res.group("ip"))
        inbound_tag_name = match_res.group("inbound_tag_name")
        outbound_tag_name = match_res.group("outbound_tag_name")
        protocol = match_res.group("protocol")
        domain = match_res.group("domain")
        port = match_res.group("port")
        period_id = match_res.group("period_id")
        profile_id = match_res.group("profile_id")

        subscription_period = models.SubscriptionPeriod.objects.filter()
        subscriptionperiodaccess_obj = models.SubscriptionPeriodAccess()
        subscriptionperiodaccess_obj.inbound_tag_name = inbound_tag_name
        subscriptionperiodaccess_obj.outbound_tag_name = outbound_tag_name
        subscriptionperiodaccess_obj.dest_address = domain
        subscriptionperiodaccess_obj.dest_port = port
        subscriptionperiodaccess_obj.dest_protocol = protocol
        subscriptionperiodaccess_obj.source_ip = ip
        subscriptionperiodaccess_obj.subscription_period_id = period_id
        subscriptionperiodaccess_obj.accessed_at = datetime_
        subscriptionperiodaccess_obj_list.append(subscriptionperiodaccess_obj)
    models.SubscriptionPeriodAccess.objects.bulk_create(subscriptionperiodaccess_obj_list)

pattern = r"""
    (?P<time>\d{2}:\d{2}:\d{2})                 # time
    .*?from\s+
    (?P<ip>
        (?:                                     # start IPv6 or IPv4
            (?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}    # IPv6
            |
            \d{1,3}(?:\.\d{1,3}){3}             # or IPv4
        )
    )
    :\d+                                       # port number (ignored)
    .*?email:\s+
    (?P<email>\S+)                             # email
"""


@app.task
def clear_subscriptionperiodaccesses(longer_than_seconds: int = 10 * 24 * 60 * 60):
    timepoint = timezone.now() - timedelta(seconds=longer_than_seconds)
    qs = models.SubscriptionPeriodAccess.objects.filter(accessed_at__lt=timepoint)
    deleted_objs = qs.delete()
    return str(deleted_objs)
