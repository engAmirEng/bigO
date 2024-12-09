import json
from datetime import timedelta

from asgiref.sync import async_to_sync

import aiogram
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from config import settings
from config.celery_app import app
from django.core.cache import cache
from django.db.models import Subquery
from django.template.loader import render_to_string
from django.utils import timezone

from ..users.models import User
from . import models


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
