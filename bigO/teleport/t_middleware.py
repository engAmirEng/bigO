from collections.abc import Awaitable, Callable
from typing import Any

import aiogram
from aiogram import BaseMiddleware
from bigO.utils import calander_type
from django.utils import timezone, translation

from . import models


class TimeZoneMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[aiogram.types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: aiogram.types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        panel_obj: models.Panel = data["panel_obj"]
        preferred_timezone = panel_obj.agency.default_timezone
        if preferred_timezone:
            timezone.activate(preferred_timezone)
        response = await handler(event, data)
        if preferred_timezone:
            timezone.deactivate()
        return response


class LanguageMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[aiogram.types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: aiogram.types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        panel_obj: models.Panel = data["panel_obj"]
        preferred_language = panel_obj.agency.default_language
        if preferred_language:
            translation.activate(preferred_language)
        response = await handler(event, data)
        if preferred_language:
            translation.deactivate()
        return response


class CalendarMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[aiogram.types.TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: aiogram.types.TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        panel_obj: models.Panel = data["panel_obj"]
        preferred_calendar_type = panel_obj.agency.default_calendar_type
        if preferred_calendar_type:
            calander_type.activate(preferred_calendar_type)
        response = await handler(event, data)
        if preferred_calendar_type:
            calander_type.deactivate()
        return response
