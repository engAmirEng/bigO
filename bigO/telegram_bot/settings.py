from environ import environ

from aiogram.client.session.aiohttp import AiohttpSession

env = environ.Env()

TELEGRAM_WEBHOOK_URL_PREFIX = env.str("TELEGRAM_WEBHOOK_URL_PREFIX", "telegram-webhook")
TELEGRAM_PROXY = env.url("TELEGRAM_PROXY", default=None)
if TELEGRAM_PROXY:
    TELEGRAM_PROXY = environ.urlunparse(TELEGRAM_PROXY)

TELEGRAM_MIDDLEWARE = [
    "bigO.telegram_bot.t_middleware.TelemetryMiddleware",
    "bigO.telegram_bot.t_middleware.CommonMiddleware",
    "bigO.telegram_bot.t_middleware.AuthenticationMiddleware",
    "bigO.telegram_bot.t_middleware.TimeZoneMiddleware",
]

TELEGRAM_SESSION = AiohttpSession(proxy=TELEGRAM_PROXY)
REDIS_STORAGE_URL = env.str("REDIS_URL")
