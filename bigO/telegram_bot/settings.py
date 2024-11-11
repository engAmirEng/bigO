from aiogram.client.session.aiohttp import AiohttpSession
from environ import environ

env = environ.Env()

TELEGRAM_WEBHOOK_URL_PREFIX = env.str("TELEGRAM_WEBHOOK_URL_PREFIX", "telegram-webhook")
TELEGRAM_PROXY = env.url("TELEGRAM_PROXY", default=None)
if TELEGRAM_PROXY:
    TELEGRAM_PROXY = environ.urlunparse(TELEGRAM_PROXY)

TELEGRAM_MIDDLEWARE = []
TELEGRAM_WEBHOOK_FLYING_DOMAINS = env.list("TELEGRAM_WEBHOOK_FLYING_DOMAINS")
TELEGRAM_PREFER_REPLY_TO_WEBHOOK = env.bool("TELEGRAM_PREFER_REPLY_TO_WEBHOOK")
TELEGRAM_SESSION = AiohttpSession(proxy=TELEGRAM_PROXY)
