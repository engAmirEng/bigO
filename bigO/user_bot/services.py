import telethon.errors.rpcerrorlist
from asgiref.sync import sync_to_async

import aiogram.client.session.aiohttp
from bigO.telegram_bot import settings
from django.utils.translation import gettext

from . import models
from .telegram.utils import Session


class NoOwnerToAuthException(Exception):
    pass


class WaitToAuthException(Exception):
    pass


async def get_telegram_session(taccount: models.TelegramAccount, tapp: models.TelegramApp) -> telethon.TelegramClient:
    session, created = await models.TelegramSession.objects.aget_or_create(account=taccount, app=tapp)
    session = Session(session=session)
    client = telethon.TelegramClient(session, tapp.api_id, tapp.api_hash, proxy=("http", "172.23.224.1", 10809, True))
    await client.connect()
    is_authed = await client.is_user_authorized()
    if is_authed:
        return client
    else:
        from bigO.telegram_bot import models as telegram_bot_models

        owners = [i async for i in taccount.owners.all()]
        if not owners:
            raise Exception()
        async with aiogram.client.session.aiohttp.AiohttpSession(proxy=settings.TELEGRAM_PROXY) as session:
            telegram_bot: telegram_bot_models.TelegramBot = taccount.account_provider.telegram_bot
            aiobot = telegram_bot.get_aiobot(session=session)
            if not owners:
                raise NoOwnerToAuthException

            from aiogram.types import InlineKeyboardButton
            from aiogram.utils.keyboard import InlineKeyboardBuilder

            req_txt = gettext("auth required for {0}, ready?").format(f"@{taccount.username}")
            ikbuilder = InlineKeyboardBuilder()
            from .tbot_communicator.dispatchers import AuthRequestCallbackData

            ikbuilder.row(
                InlineKeyboardButton(
                    text=gettext("yes"),
                    callback_data=AuthRequestCallbackData(
                        app_id=str(tapp.id), account_id=str(taccount.id), ok=True
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=gettext("no"),
                    callback_data=AuthRequestCallbackData(
                        app_id=str(tapp.id), account_id=str(taccount.id), ok=False
                    ).pack(),
                ),
            )
            tel_sent_count = 0
            for owner in owners:
                tuser = await telegram_bot_models.TelegramUser.objects.filter(
                    bot=taccount.account_provider.telegram_bot, user=owner
                ).afirst()
                if tuser is None:
                    continue

                await aiobot.send_message(chat_id=tuser.tid, text=req_txt, reply_markup=ikbuilder.as_markup())
                tel_sent_count += 0
            raise WaitToAuthException
