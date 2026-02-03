from environ import environ

import aiogram.client.session.aiohttp

from . import metrics


class AiohttpSession(aiogram.client.session.aiohttp.AiohttpSession):
    async def make_request(
        self,
        bot: aiogram.Bot,
        method: aiogram.methods.TelegramMethod[aiogram.methods.base.TelegramType],
        *args,
        **kwargs,
    ):
        """
        metrics added
        """
        from . import models

        bot_obj = await models.TelegramBot.objects.filter(tid=bot.id).afirst()
        metric_attrs = None
        if bot_obj:
            metric_attrs = {
                "bot_id": bot_obj.id,
                "method_name": method.__api_method__,
            }
        try:
            res = await super().make_request(*args, bot=bot, method=method, **kwargs)
        except Exception as e:
            if metric_attrs:
                metric_attrs["error_type"] = e.__class__.__name__
                metrics.method_total_counter.add(
                    1,
                    attributes=metric_attrs,
                )
            raise e
        else:
            if metric_attrs:
                metrics.method_total_counter.add(
                    1,
                    attributes=metric_attrs,
                )
            return res


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
