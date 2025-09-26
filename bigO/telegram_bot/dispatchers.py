import os

from redis.asyncio import Redis

from aiogram import Dispatcher
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from bigO.teleport.dispatchers import router as teleport_router

fsm_storage = RedisStorage(Redis.from_url(os.getenv("REDIS_URL")), key_builder=DefaultKeyBuilder(with_bot_id=True))

dp = Dispatcher(storage=fsm_storage)
dp.include_router(teleport_router)
