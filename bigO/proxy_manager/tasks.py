import datetime
import re
import zoneinfo
from datetime import timedelta
from decimal import Decimal
from typing import Any

import influxdb_client
import sentry_sdk

from bigO.node_manager import models as node_manager_models
from config.celery_app import app
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from . import models, services


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
    config = models.Config.get_solo()
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

        if config.usage_correction_factor:
            new_flow_download_bytes = int(new_flow_download_bytes * config.usage_correction_factor)
            new_flow_upload_bytes = int(new_flow_upload_bytes * config.usage_correction_factor)

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
        config = models.Config.get_solo()
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
                dl_df = df[df["_field"] == "dl_bytes"]
                between_download_bytes = dl_df.iloc[0].to_dict()["_value"] if not dl_df.empty else 0
                up_df = df[df["_field"] == "up_bytes"]
                between_upload_bytes = up_df.iloc[0].to_dict()["_value"] if not up_df.empty else 0

                if config.usage_correction_factor:
                    between_download_bytes = int(between_download_bytes * config.usage_correction_factor)
                    between_upload_bytes = int(between_upload_bytes * config.usage_correction_factor)

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
def handle_xray_conf(node_id: int, xray_lines: str, base_labels: dict[str, Any]):
    alive_outbound_observatory_pattern = r"""(?P<datetime_str>\d{4}\/\d{2}\/\d{2}[ ]\d{2}:\d{2}:\d{2}\.\d{6}).*app\/observatory:[ ]the outbound[ ](?P<outbound_name>.*)[ ]is[ ]alive:(?P<delay_secs>.*)"""
    dead_outbound_observatory_pattern = r"(?P<datetime_str>\d{4}\/\d{2}\/\d{2}[ ]\d{2}:\d{2}:\d{2}\.\d{6}).*app\/observatory:[ ]the outbound[ ](?P<outbound_name>.*)[ ]is[ ]dead:(?P<description>.*)"
    node = node_manager_models.Node.objects.get(id=node_id)
    points: list[influxdb_client.Point] = []
    for line in xray_lines.split("\n"):
        observatory_checked = False
        if not line:
            continue
        if (
            not observatory_checked
            and (match_res := re.search(alive_outbound_observatory_pattern, line))
            and len(match_res.groups()) == 3
        ):
            point = influxdb_client.Point("connection_health")
            observatory_checked = True
            datetime_str = match_res.group("datetime_str")
            outbound_name = match_res.group("outbound_name")
            delay_secs = Decimal(match_res.group("delay_secs"))
            time_ = datetime.datetime.strptime(datetime_str, "%Y/%m/%d %H:%M:%S.%f").replace(
                tzinfo=zoneinfo.ZoneInfo("UTC")
            )
            point.time(
                time_,
                write_precision=influxdb_client.domain.write_precision.WritePrecision.S,
            )
            services.set_outbound_tags(point=point, node=node, outbound_name=outbound_name)
            point.field("status", "ok")
            point.tag("status", "ok")
            point.field("delay", delay_secs * 1000)
            points.append(point)

        if (
            not observatory_checked
            and (match_res := re.search(dead_outbound_observatory_pattern, line))
            and len(match_res.groups()) == 3
        ):
            point = influxdb_client.Point("connection_health")
            observatory_checked = True
            datetime_str = match_res.group("datetime_str")
            outbound_name = match_res.group("outbound_name")
            description = match_res.group("description")
            time_ = datetime.datetime.strptime(datetime_str, "%Y/%m/%d %H:%M:%S.%f").replace(
                tzinfo=zoneinfo.ZoneInfo("UTC")
            )
            point.time(
                time_,
                write_precision=influxdb_client.domain.write_precision.WritePrecision.S,
            )
            services.set_outbound_tags(point=point, node=node, outbound_name=outbound_name)
            point.field("status", "timeout")
            point.tag("status", "timeout")
            points.append(point)

    if not points:
        return "no points!!!"
    with influxdb_client.InfluxDBClient(
        url=settings.INFLUX_URL, token=settings.INFLUX_TOKEN, org=settings.INFLUX_ORG
    ) as _client:
        with _client.write_api(
            write_options=influxdb_client.WriteOptions(
                batch_size=500,
                flush_interval=10_000,
                jitter_interval=2_000,
                retry_interval=5_000,
                max_retries=3,
                max_retry_delay=30_000,
                max_close_wait=300_000,
                exponential_base=2,
            )
        ) as _write_client:
            _write_client.write(settings.INFLUX_BUCKET, settings.INFLUX_ORG, points)
