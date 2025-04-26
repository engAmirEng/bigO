import os
import sys
import json
import pathlib
import tempfile
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

import django.template
import influxdb_client.domain.write_precision
import requests.adapters
import requests.auth
from asgiref.sync import async_to_sync

import aiogram
from django.db import transaction
import ansible_runner
from django.urls import reverse

import bigO.utils.logging
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from bigO.core import models as core_models
from config import settings
from config.celery_app import app
from django.core.cache import cache
from django.db.models import Subquery
from django.template.loader import render_to_string
from django.utils import timezone

from ..users.models import User
from . import models, typing


@app.task
def check_node_latest_sync(*, limit_seconds: int, ignore_node_ids: list[int] | None = None):
    superuser = User.objects.filter(is_superuser=True, telegram_chat_tid__isnull=False).first()
    if not superuser:
        return "no_superuser_to_send"
    now = timezone.now()
    limit_seconds = timedelta(seconds=limit_seconds)
    ignore_node_ids = ignore_node_ids or []
    all_offlines_qs = models.NodeLatestSyncStat.objects.filter(respond_at__lt=now - limit_seconds)
    reporting_offlines_qs = all_offlines_qs.exclude(node_id__in=ignore_node_ids)
    perv_offline_nodes = cache.get("offline_nodes")
    back_onlines_qs = models.NodeLatestSyncStat.objects.none()
    if perv_offline_nodes:
        perv_offline_node_ids = json.loads(perv_offline_nodes)
        back_onlines_qs = models.NodeLatestSyncStat.objects.filter(node_id__in=perv_offline_node_ids).exclude(
            id__in=Subquery(all_offlines_qs.values("id"))
        )

    if reporting_offlines_qs.count() == 0 and not back_onlines_qs.exists():
        return "all_good"

    message = render_to_string(
        "node_manager/annonces/node_latest_sync.thtml",
        context={
            "limit_timedelta": limit_seconds,
            "reporting_offlines_qs": reporting_offlines_qs,
            "back_online_qs": back_onlines_qs,
        },
    )

    async def inner():
        async with AiohttpSession() as session:
            bot = aiogram.Bot(settings.TELEGRAM_BOT_TOKEN, session=session, parse_mode=ParseMode.HTML)
            await bot.send_message(chat_id=superuser.telegram_chat_tid, text=message)

    async_to_sync(inner)()
    cache.set("offline_nodes", json.dumps([i.node_id for i in all_offlines_qs]))
    return f"{str(reporting_offlines_qs.count())} are down and {str(back_onlines_qs.count())} are back"


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

@app.task
def ansible_deploy_node(node_id: int):
    node_obj = models.Node.objects.get(id=node_id)
    o2spec = node_obj.o2spec
    deploy_snippet = o2spec.ansible_deploy_snippet
    deploy_content = django.template.Template(deploy_snippet.template).render(django.template.Context())
    assert "templateerror" not in deploy_content
    o2_binary = o2spec.program.get_program_for_node(node_obj)
    assert isinstance(o2_binary, models.ProgramBinary)

    extravars = {
        "install_dir": str(pathlib.Path(o2spec.working_dir).parent),
        "smallO2_binary_download_url": o2spec.sync_domain + reverse("node_manager:node_program_binary_content_by_hash", args=[o2_binary.hash]),
        "smallO2_binary_sha256": o2_binary.hash,
        "api_key": o2spec.api_key,
        "interval_sec": o2spec.interval_sec,
        "sync_url": o2spec.sync_url,
        "sentry_dsn": o2spec.sentry_dsn
    }

    time_str = timezone.now().astimezone(ZoneInfo("UTC")).strftime("%Y%m%d_%H%M%S")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create inventory file
        inventory_path = pathlib.Path(tmpdir, f"inventory_{time_str}")
        with open(inventory_path, "w") as f:
            ip = node_obj.node_nodepublicips.first().ip.ip.ip
            username = node_obj.ssh_user
            passwd = node_obj.ssh_pass
            line = f"{ip} ansible_user={username} ansible_password={passwd} ansible_become_pass={passwd} ansible_port={node_obj.ssh_port} ansible_ssh_common_args='-o StrictHostKeyChecking=no'\n"
            f.write(line)

        # Create playbook file
        playbook_path = pathlib.Path(tmpdir, f"playbook_{time_str}.yml")
        with open(playbook_path, "w") as f:
            f.write(deploy_content)

        an_task_obj = models.AnsibleTask()
        an_task_obj.name = "Install and start smallO2"
        an_task_obj.logs = ""
        an_task_obj.status = models.AnsibleTask.StatusChoices.STARTED
        an_task_obj.playbook_snippet = deploy_snippet
        an_task_obj.playbook_content = deploy_content
        ansibletasknode_obj = models.AnsibleTaskNode()
        ansibletasknode_obj.task = an_task_obj
        ansibletasknode_obj.node = node_obj
        with transaction.atomic(using="main"):
            an_task_obj.save()
            ansibletasknode_obj.save()
        ansibletasknode_mapping = {
            str(ip): ansibletasknode_obj
        }

        current_python_path = sys.executable
        # ansible is installed in this python env so
        os.environ["PATH"] = os.environ["PATH"] + f":{pathlib.Path(current_python_path).parent}"
        thread, runner = ansible_runner.run_async(
            extravars=extravars,
            private_data_dir=tmpdir,
            playbook=str(playbook_path),
            inventory=str(inventory_path),
        )
        for event in runner.events:
            an_task_obj.logs += ("\n" + event["stdout"])
            if (event_data := event.get("event_data")) and (host_key := event_data.get("host")) and event["event"] != "runner_on_start":
                related_ansibletasknode_obj = ansibletasknode_mapping[host_key]
                related_ansibletasknode_obj.result = related_ansibletasknode_obj.result or {}
                related_ansibletasknode_obj.result[event_data["task"]] = event
                related_ansibletasknode_obj.save()
            elif event.get("event") == 'playbook_on_stats':
                an_task_obj.result = event
            an_task_obj.save()
        thread.join()
        result = runner
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

        return result
