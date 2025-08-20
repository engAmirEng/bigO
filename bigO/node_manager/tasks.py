import datetime
import json
import os
import pathlib
import re
import sys
import urllib.parse
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

import ansible_runner
import influxdb_client.domain.write_precision
import requests.adapters
import requests.auth
import sentry_sdk
import tomli_w
from asgiref.sync import async_to_sync
from celery import current_task

import aiogram
import bigO.utils.logging
import django.template
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from bigO.core import models as core_models
from config.celery_app import app
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Subquery
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from ..users.models import User
from . import models, typing


@app.task
def check_node_latest_sync(*, limit_seconds: int, responsetime_miliseconds: int = 1_200, ignore_node_ids: list[int] | None = None):
    from bigO.core.models import SiteConfiguration

    siteconfiguration_obj = SiteConfiguration.objects.get()
    if siteconfiguration_obj.sync_brake:
        return "sync_brake is on"
    superuser = User.objects.filter(is_superuser=True, telegram_chat_tid__isnull=False).first()
    if not superuser:
        return "no_superuser_to_send"
    ignore_node_ids = ignore_node_ids or []
    # at least has one successful sync
    all_problematic_qs = (
        models.Node.objects.ann_is_online(defualt_interval_sec=limit_seconds)
        .ann_generic_status(default_acceptable_response_time=timedelta(microseconds=responsetime_miliseconds))
        .filter(
            is_revoked=False,
            generic_status__in=[models.GenericStatusChoices.OFFLINE, models.GenericStatusChoices.ATTENDED_OFFLINE, models.GenericStatusChoices.ERROR],
        )
    )
    reporting_problematic_qs = all_problematic_qs.filter(generic_status=~models.GenericStatusChoices.ATTENDED_OFFLINE).exclude(id__in=ignore_node_ids)
    perv_offline_nodes = cache.get("offline_nodes")
    back_onlines_qs = models.Node.objects.none()
    if perv_offline_nodes:
        perv_offline_node_ids = json.loads(perv_offline_nodes)
        back_onlines_qs = models.Node.objects.filter(id__in=perv_offline_node_ids).exclude(
            id__in=Subquery(all_problematic_qs.values("id"))
        )

    if reporting_problematic_qs.count() == 0 and not back_onlines_qs.exists():
        return "all_good"

    message = render_to_string(
        "node_manager/annonces/node_latest_sync.thtml",
        context={
            "reporting_offlines_qs": reporting_problematic_qs,
            "back_online_qs": back_onlines_qs,
        },
    )

    async def inner():
        async with AiohttpSession() as session:
            bot = aiogram.Bot(settings.TELEGRAM_BOT_TOKEN, session=session, parse_mode=ParseMode.HTML)
            await bot.send_message(chat_id=superuser.telegram_chat_tid, text=message)

    async_to_sync(inner)()
    cache.set("offline_nodes", json.dumps([i.id for i in all_problematic_qs]))
    return f"{str(reporting_problematic_qs.count())} are down and {str(back_onlines_qs.count())} are back"


@app.task
def handle_goingto(node_id: int, goingto_json_lines: str, base_labels: dict[str, Any]):
    from bigO.proxy_manager.services import set_internal_user_last_stat, set_profile_last_stat

    points: list[influxdb_client.Point] = []
    for line in goingto_json_lines.split("\n"):
        if not line:
            continue
        try:
            res = json.loads(line)
        except json.JSONDecodeError as e:
            # most likely due to offset log tailing
            sentry_sdk.capture_exception(
                Exception(f"error in decoding goingto stdout line: err is {e} and line is {line}")
            )
            continue
        else:
            if res["result_type"] == "xray_raw_traffic_v1":
                collect_time = datetime.datetime.fromisoformat(res["timestamp"])
                user_points: dict[str, influxdb_client.Point] = {}
                internal_user_points: dict[str, influxdb_client.Point] = {}
                inbound_points: dict[str, influxdb_client.Point] = {}
                outbound_points: dict[str, influxdb_client.Point] = {}
                res = typing.GoingtoXrayRawTrafficV1JsonOutPut(**json.loads(res["msg"]))
                for stat in res.stats:
                    if not stat.name or not stat.value:
                        continue
                    user_traffic_regex = r"user>>>period(\d+)\.profile(\d+)[^>]+>>>traffic>>>(downlink|uplink)"
                    user_with_id_traffic_regex = (
                        r"user>>>period(\d+)\.profile(\d+).user(\d+)[^>]+>>>traffic>>>(downlink|uplink)"
                    )
                    internal_user_traffic_regex = r"user>>>rule(\d+)\.node(\d+)[^>]+>>>traffic>>>(downlink|uplink)"
                    inbound_traffic_regex = r"inbound>>>([^>]+)>>>traffic>>>(downlink|uplink)"
                    outbound_traffic_regex = r"outbound>>>([^>]+)>>>traffic>>>(downlink|uplink)"
                    if (
                        len(user_matches := re.findall(user_traffic_regex, stat.name)) == 1
                        or len(user_with_id_matches := re.findall(user_with_id_traffic_regex, stat.name)) == 1
                    ):
                        user_id = None
                        if len(user_matches) == 1:
                            period_id = str(user_matches[0][0])
                            profile_id = str(user_matches[0][1])
                            downlink_or_uplink = user_matches[0][2]
                        elif len(user_with_id_matches) == 1:
                            period_id = str(user_with_id_matches[0][0])
                            profile_id = str(user_with_id_matches[0][1])
                            user_id = str(user_with_id_matches[0][2])
                            downlink_or_uplink = user_with_id_matches[0][3]
                        else:
                            raise AssertionError
                        set_profile_last_stat(
                            sub_profile_id=profile_id, sub_profile_period_id=period_id, collect_time=collect_time
                        )
                        key = f"{profile_id}.{period_id}"

                        point = user_points.get(key)
                        if point is None:
                            point = influxdb_client.Point("xray_usage")
                            point.time(
                                collect_time,
                                write_precision=influxdb_client.domain.write_precision.WritePrecision.S,
                            )
                            user_points[key] = point
                            point.tag("usage_type", "user")
                            if user_id:
                                point.tag("user_id", user_id)
                            point.tag("profile_id", profile_id)
                            point.tag("period_id", period_id)
                            for tag_name, tag_value in base_labels.items():
                                point.tag(tag_name, tag_value)
                        if downlink_or_uplink == "downlink":
                            point.field("dl_bytes", stat.value)
                        elif downlink_or_uplink == "uplink":
                            point.field("up_bytes", stat.value)
                        else:
                            raise AssertionError(f"{stat.value=} is not downlink or uplink")
                    elif len(internal_user_matches := re.findall(internal_user_traffic_regex, stat.name)) == 1:
                        rule_id = internal_user_matches[0][0]
                        node_user_id = internal_user_matches[0][1]
                        downlink_or_uplink = internal_user_matches[0][2]
                        set_internal_user_last_stat(
                            rule_id=rule_id, node_user_id=node_user_id, collect_time=collect_time
                        )
                        key = f"{rule_id}.{node_user_id}"

                        point = internal_user_points.get(key)
                        if point is None:
                            point = influxdb_client.Point("xray_usage")
                            point.time(
                                collect_time,
                                write_precision=influxdb_client.domain.write_precision.WritePrecision.S,
                            )
                            internal_user_points[key] = point
                            point.tag("usage_type", "internal_user")
                            point.tag("rule_id", rule_id)
                            point.tag("node_user_id", node_user_id)

                            for tag_name, tag_value in base_labels.items():
                                point.tag(tag_name, tag_value)
                        if downlink_or_uplink == "downlink":
                            point.field("dl_bytes", stat.value)
                        elif downlink_or_uplink == "uplink":
                            point.field("up_bytes", stat.value)
                        else:
                            raise AssertionError(f"{stat.value=} is not downlink or uplink")
                    elif len(inbound_matches := re.findall(inbound_traffic_regex, stat.name)) == 1:
                        inbound_tag = inbound_matches[0][0]
                        downlink_or_uplink = inbound_matches[0][1]
                        point = inbound_points.get(inbound_tag)
                        if point is None:
                            point = influxdb_client.Point("xray_usage")
                            point.time(
                                collect_time,
                                write_precision=influxdb_client.domain.write_precision.WritePrecision.S,
                            )
                            inbound_points[inbound_tag] = point
                            point.tag("usage_type", "inbound")
                            point.tag("inbound_tag", inbound_tag)
                            for tag_name, tag_value in base_labels.items():
                                point.tag(tag_name, tag_value)
                        if downlink_or_uplink == "downlink":
                            point.field("dl_bytes", stat.value)
                        elif downlink_or_uplink == "uplink":
                            point.field("up_bytes", stat.value)
                        else:
                            raise AssertionError(f"{stat.value=} is not downlink or uplink")
                    elif len(outbound_matches := re.findall(outbound_traffic_regex, stat.name)) == 1:
                        outbound_tag = outbound_matches[0][0]
                        downlink_or_uplink = outbound_matches[0][1]
                        point = outbound_points.get(outbound_tag)
                        if point is None:
                            point = influxdb_client.Point("xray_usage")
                            point.time(
                                collect_time,
                                write_precision=influxdb_client.domain.write_precision.WritePrecision.S,
                            )
                            outbound_points[outbound_tag] = point
                            point.tag("usage_type", "outbound")
                            point.tag("outbound_tag", outbound_tag)
                            for tag_name, tag_value in base_labels.items():
                                point.tag(tag_name, tag_value)
                        if downlink_or_uplink == "downlink":
                            point.field("dl_bytes", stat.value)
                        elif downlink_or_uplink == "uplink":
                            point.field("up_bytes", stat.value)
                        else:
                            raise AssertionError(f"{stat.value=} is not downlink or uplink")
                    else:
                        continue
                        # raise NotImplementedError
                points.extend(
                    [
                        *user_points.values(),
                        *internal_user_points.values(),
                        *inbound_points.values(),
                        *outbound_points.values(),
                    ]
                )

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


@app.task
def telegraf_to_influx_send(telegraf_json_lines: str, base_labels: dict[str, Any]):
    points: list[influxdb_client.Point] = []
    for line in telegraf_json_lines.split("\n"):
        try:
            res = json.loads(line)
        except json.JSONDecodeError:
            pass
        else:
            res = typing.TelegrafJsonOutPut(**res)
            for metric in res.metrics:
                point = influxdb_client.Point(metric.name)
                for tag_name, tag_value in {**metric.tags, **base_labels}.items():
                    point = point.tag(tag_name, tag_value)
                for field_name, field_value in metric.fields.items():
                    if isinstance(field_value, int):
                        field_value = float(field_value)
                    point = point.field(field_name, field_value)
                point.time(
                    metric.timestamp,
                    write_precision=influxdb_client.domain.write_precision.WritePrecision.S,
                )
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


@app.task
def send_to_loki(streams: list[typing.LokiStram]):
    requests_session = requests.Session()
    retries = requests.adapters.Retry(total=5, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504, 598])
    requests_session.mount("https://", requests.adapters.HTTPAdapter(max_retries=retries))
    site_config = core_models.SiteConfiguration.objects.get()
    streams_list = bigO.utils.logging.split_by_total_length(streams, site_config.loki_batch_size)
    for streams in streams_list:
        payload = {"streams": streams}
        headers = {"Content-Type": "application/json"}
        res = requests_session.post(
            settings.LOKI_PUSH_ENDPOINT,
            headers=headers,
            json=payload,
            auth=requests.auth.HTTPBasicAuth(settings.LOKI_USERNAME, settings.LOKI_PASSWORD),
        )
        if not res.ok:
            raise Exception(f"faild send to Loki, {res.text=}")


@app.task(soft_time_limit=15 * 60, time_limit=16 * 60)
def ansible_deploy_node(node_id: int):
    celery_task_id = current_task.request.id

    node_obj = models.Node.objects.get(id=node_id)
    o2spec = node_obj.o2spec
    try:
        nodesyncstat_obj = node_obj.node_nodesyncstat
    except models.NodeLatestSyncStat.DoesNotExist:
        nodesyncstat_obj = None
    if o2spec.keep_latest_config and nodesyncstat_obj is not None and nodesyncstat_obj.config:
        raw_toml_config = tomli_w.dumps({k: v for k, v in nodesyncstat_obj.config.items() if v is not None})
    else:
        raw_toml_config = ""

    deploy_snippet = node_obj.ansible_deploy_snippet
    deploy_content = django.template.Template(deploy_snippet.template).render(
        django.template.Context({"node_obj": node_obj})
    )
    assert "templateerror" not in deploy_content

    ips = [i.ip.ip.ip for i in node_obj.node_nodepublicips.all()]
    ips.sort(key=lambda x: x.version, reverse=False)
    ip = ips[0]
    username = node_obj.ssh_user
    passwd = node_obj.ssh_pass
    inventory_content = f"{node_obj.name} ansible_host={ip} ansible_user={username} ansible_password='{passwd}' ansible_become_pass={passwd} ansible_port={node_obj.ssh_port} ansible_ssh_common_args='-o StrictHostKeyChecking=no'\n"

    o2_binary = o2spec.program.get_program_for_node(node_obj)
    if o2_binary is None or not isinstance(o2_binary, models.ProgramBinary):
        raise Exception(f"no ProgramBinary of {o2spec.program=} found for {node_obj=}")

    ssh_keys_raw = ",".join([i.content for i in node_obj.ssh_public_keys.all()])
    extravars = {
        "ssh_keys_raw": ssh_keys_raw,
        "install_dir": str(pathlib.Path(o2spec.working_dir).parent),
        "smallO2_binary_download_url": urllib.parse.urljoin(
            o2spec.sync_domain, reverse("node_manager:node_program_binary_content_by_hash", args=[o2_binary.hash])
        ),
        "smallO2_binary_sha256": o2_binary.hash,
        "raw_toml_config": raw_toml_config,
        "api_key": o2spec.api_key,
        "interval_sec": o2spec.interval_sec,
        "sync_url": o2spec.sync_url,
        "sentry_dsn": o2spec.sentry_dsn,
    }

    an_task_obj = models.AnsibleTask()
    an_task_obj.name = "Install and start smallO2"
    an_task_obj.celery_task_id = celery_task_id
    an_task_obj.logs = ""
    an_task_obj.status = models.AnsibleTask.StatusChoices.STARTED
    an_task_obj.playbook_snippet = deploy_snippet
    an_task_obj.playbook_content = deploy_content
    an_task_obj.inventory_content = inventory_content
    an_task_obj.extravars = extravars
    ansibletasknode_obj = models.AnsibleTaskNode()
    ansibletasknode_obj.task = an_task_obj
    ansibletasknode_obj.node = node_obj
    with transaction.atomic(using="main"):
        an_task_obj.save()
        ansibletasknode_obj.save()

    time_str = timezone.now().astimezone(ZoneInfo("UTC")).strftime("%Y%m%d_%H%M%S")
    workdir: pathlib.Path = settings.ANSIBLE_WORKING_DIR
    tasks_assets_dir = workdir.joinpath("tasks_assets")
    tasks_assets_dir.mkdir(exist_ok=True)
    # Create inventory file
    inventory_path = tasks_assets_dir.joinpath(f"inventory_{an_task_obj.id}_{time_str}")
    with open(inventory_path, "w") as f:
        f.write(inventory_content)
    # Create playbook file
    playbook_path = tasks_assets_dir.joinpath(f"playbook_{an_task_obj.id}_{time_str}.yml")
    with open(playbook_path, "w") as f:
        f.write(deploy_content)

    ansibletasknode_mapping = {node_obj.name: ansibletasknode_obj}

    current_python_path = sys.executable
    # ansible is installed in this python env so
    os.environ["PATH"] = os.environ["PATH"] + f":{pathlib.Path(current_python_path).parent}"
    thread, runner = ansible_runner.run_async(
        extravars=extravars,
        private_data_dir=str(workdir),
        playbook=str(playbook_path),
        inventory=str(inventory_path),
    )
    for event in runner.events:
        an_task_obj.logs += "\n" + event["stdout"]
        if (
            (event_data := event.get("event_data"))
            and (host_key := event_data.get("host"))
            and (event["event"] != "runner_on_start")
        ):
            related_ansibletasknode_obj = ansibletasknode_mapping[host_key]
            related_ansibletasknode_obj.result = related_ansibletasknode_obj.result or {}
            related_ansibletasknode_obj.result["tasks"] = related_ansibletasknode_obj.result.get("tasks", [])
            related_ansibletasknode_obj.result["tasks"].append({event_data["task"]: event})
            related_ansibletasknode_obj.save()
        elif event.get("event") == "playbook_on_stats":
            an_task_obj.result = event
        an_task_obj.save()
    thread.join()
    result = runner
    if result.stats:
        for stat_key, host_mapping in result.stats.items():
            for host_key, count in host_mapping.items():
                related_ansibletasknode_obj = ansibletasknode_mapping[host_key]
                if not hasattr(related_ansibletasknode_obj, stat_key):
                    # 'processed', 'rescued', 'skipped', 'ignored'
                    continue
                # 'ok', 'dark', 'failures', 'changed'
                setattr(related_ansibletasknode_obj, stat_key, count)
        for k, v in ansibletasknode_mapping.items():
            v.save()
    an_task_obj.status = models.AnsibleTask.StatusChoices.FINISHED
    an_task_obj.finished_at = timezone.now()
    an_task_obj.save()

    return result.status
