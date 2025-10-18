import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import aiogram
from django.core.management import BaseCommand
from django.utils import autoreload

from ... import dispatchers, models


class Command(BaseCommand):
    help = "Starts telegram bot polling"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reload",
            dest="use_reloader",
            action="store_true",
            default=False,
            help="To use the auto-reloader.",
        )

    def handle(self, *args, **options):
        if options["use_reloader"]:
            autoreload.run_with_reloader(self.run, handle_signals=False)
        else:
            self.run(handle_signals=True)

    def run(self, handle_signals: bool):
        HELPER_MONKEY_ATTR = "bot_obj_monkey"
        first_10_telegram_bots = list(models.TelegramBot.objects.all()[:10])

        class PollingNormalizerMiddleware(aiogram.BaseMiddleware):
            async def __call__(
                self,
                handler: Callable[[aiogram.types.TelegramObject, dict[str, Any]], Awaitable[Any]],
                event: aiogram.types.TelegramObject,
                data: dict[str, Any],
            ) -> Any:
                bot: aiogram.Bot = data["bot"]
                bot_obj = getattr(bot, HELPER_MONKEY_ATTR)
                data.update({"aiobot": bot, "bot_obj": bot_obj})
                return await handler(event, data)

        async def main() -> None:
            aiobots = []
            for i in first_10_telegram_bots:
                aiobot = i.get_aiobot()
                setattr(aiobot, HELPER_MONKEY_ATTR, i)
                aiobots.append(aiobot)
            dispatchers.dp.update.middleware._middlewares.insert(0, PollingNormalizerMiddleware())
            await dispatchers.dp.start_polling(*aiobots, handle_signals=handle_signals)

        asyncio.run(main())
