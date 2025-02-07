import json
from datetime import timedelta
from typing import Any

import influxdb_client.domain.write_precision
import requests.adapters
import requests.auth
from asgiref.sync import async_to_sync

import aiogram
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
    session = AiohttpSession()
    bot = aiogram.Bot(settings.TELEGRAM_BOT_TOKEN, session=session, parse_mode=ParseMode.HTML)
    async_to_sync(session.close)()
    async_to_sync(bot.send_message)(chat_id=superuser.telegram_chat_tid, text=message)
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
        finally:
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
