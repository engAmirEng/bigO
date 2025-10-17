import os
from typing import Any, Awaitable, Callable

from redis.asyncio import Redis

from aiogram import Dispatcher
from aiogram import Router as BaseRouter
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage

fsm_storage = RedisStorage(Redis.from_url(os.getenv("REDIS_URL")), key_builder=DefaultKeyBuilder(with_bot_id=True))

dp = Dispatcher(storage=fsm_storage)


class AppRouter(BaseRouter):
    def __init__(self, *args, app_filter_callback: Callable[[Any], Awaitable[bool]], **kwargs):
        super().__init__(*args, **kwargs)
        self.app_filter_callback = app_filter_callback

    async def propagate_event(self, *args, **kwargs):
        handle = await self.app_filter_callback(*args, **kwargs)
        if not handle:
            return UNHANDLED
        return await super().propagate_event(*args, **kwargs)
