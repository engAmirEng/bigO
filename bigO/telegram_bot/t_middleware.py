from collections.abc import Awaitable, Callable
from typing import Any

import aiogram
from aiogram import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from django.utils.translation import gettext as _

from . import models
from .models import TelegramUser


class CommonMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[aiogram.types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: aiogram.types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        event_chat: aiogram.types.Chat = data["event_chat"]
        event_from_user: aiogram.types.User = data["event_from_user"]
        bot_obj: models.TelegramBot = data["bot_obj"]
        aiobot: aiogram.Bot = data["aiobot"]
        if bot_obj.is_powered_off:
            text = _("ربات خاموش است")
            await aiobot.send_message(chat_id=event_chat.id, text=text)
            return
        return await handler(event, data)


class AuthenticationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[aiogram.types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: aiogram.types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        event_chat: aiogram.types.Chat = data["event_chat"]
        event_from_user: aiogram.types.User = data["event_from_user"]
        bot_obj: models.TelegramBot = data["bot_obj"]
        tuser = None
        try:
            tuser = (
                await TelegramUser.objects.filter(user_tid=event_from_user.id, tbot_id=bot_obj.id)
                .select_related("tbot", "user")
                .aget()
            )
        except TelegramUser.DoesNotExist:
            tuser = None

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
        if tuser and (preferred_timezone := tuser.user.preferred_timezone):
            timezone.activate(preferred_timezone)
        response = await handler(event, data)
        timezone.deactivate()
        return response
