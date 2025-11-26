import re
from collections.abc import Awaitable, Callable
from typing import Any

import aiogram
from aiogram import BaseMiddleware
from django.utils import timezone
from django.utils.translation import gettext as _

from . import metrics, models
from .models import TelegramUser


class CommonMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[aiogram.types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: aiogram.types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        event_from_user: aiogram.types.User = data["event_from_user"]
        bot_obj: models.TelegramBot = data["bot_obj"]
        aiobot: aiogram.Bot = data["aiobot"]
        if bot_obj.is_powered_off:
            text = _("ربات خاموش است")
            await aiobot.send_message(chat_id=event_from_user.id, text=text)
            return
        return await handler(event, data)


class AuthenticationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[aiogram.types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: aiogram.types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        event_from_user: aiogram.types.User = data["event_from_user"]
        bot_obj: models.TelegramBot = data["bot_obj"]
        created, tuser = await TelegramUser.from_update(bot_obj=bot_obj, tuser=event_from_user)

        data.update(tuser=tuser)
        return await handler(event, data)


class TimeZoneMiddleware(BaseMiddleware):
    # place after AuthenticationMiddleware
    async def __call__(
        self,
        handler: Callable[[aiogram.types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: aiogram.types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tuser: models.TelegramUser = data["tuser"]
        if tuser and tuser.user and (preferred_timezone := tuser.user.preferred_timezone):
            timezone.activate(preferred_timezone)
        response = await handler(event, data)
        if tuser and tuser.user and (preferred_timezone := tuser.user.preferred_timezone):
            timezone.deactivate()
        return response


class TelemetryMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[aiogram.types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: aiogram.types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot_obj: models.TelegramBot = data["bot_obj"]
        metrics.update_total_counter.add(
            1, attributes={"bot_id": bot_obj.id, "update_type": resolve_update_type(event)}
        )
        response = await handler(event, data)
        return response


def resolve_update_type(event: aiogram.types.TelegramObject) -> str:
    """Best-effort resolution of the update type."""

    if hasattr(event, "event_type"):
        update_type = getattr(event, "event_type")
        if isinstance(update_type, str):
            return sanitize_label(update_type)
    if hasattr(event, "update_type"):
        update_type = getattr(event, "update_type")
        if isinstance(update_type, str):
            return sanitize_label(update_type)
    if hasattr(event, "message"):
        return "message"
    if hasattr(event, "callback_query"):
        return "callback_query"
    name = event.__class__.__name__ if hasattr(event, "__class__") else "update"
    return sanitize_label(name.lower())


def sanitize_label(value: str | None) -> str:
    """Normalize a label value by stripping illegal characters and length."""
    _MAX_LABEL_LENGTH = 80
    _ALLOWED_RE = re.compile(r"[^a-zA-Z0-9_:]+")

    if not value:
        return "unknown"
    cleaned = _ALLOWED_RE.sub("_", value)
    if len(cleaned) > _MAX_LABEL_LENGTH:
        cleaned = cleaned[:_MAX_LABEL_LENGTH]
    return cleaned
