import asyncio
import io
import tempfile

import makefun
import telethon
from asgiref.sync import sync_to_async
from qrcode import QRCode
from telethon.sessions import StringSession

import aiogram.utils.deep_linking
from aiogram import Bot
from aiogram.filters import CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, CopyTextButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from bigO.proxy_manager import models as proxy_manager_models
from bigO.telegram_bot.dispatchers import AppRouter
from bigO.telegram_bot.models import TelegramBot, TelegramUser
from bigO.telegram_bot.utils import thtml_render_to_string
from django.utils.translation import gettext

from .. import models
from ..telegram.utils import Session


async def app_filter_callback(*args, **kwargs):
    bot_obj: TelegramBot | None = kwargs.get("bot_obj")
    if bot_obj is None:
        return False, args, kwargs
    try:
        accountprovider_obj = await models.AccountProvider.objects.aget(telegram_bot=bot_obj)
    except models.AccountProvider.DoesNotExist:
        return False, args, kwargs
    return True, args, {**kwargs, "accountprovider_obj": accountprovider_obj}


router = AppRouter(name="user_bot", app_filter_callback=app_filter_callback)


class AuthRequestCallbackData(CallbackData, prefix="auth_request"):
    app_id: str
    account_id: str
    ok: bool


@router.callback_query(AuthRequestCallbackData.filter())
async def menu_handler(
    message: CallbackQuery,
    callback_data: AuthRequestCallbackData,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    accountprovider_obj: models.AccountProvider,
) -> aiogram.methods.TelegramMethod | None:
    if callback_data.ok:
        taccount = await models.TelegramAccount.objects.filter(id=callback_data.account_id, owners=tuser.user).afirst()
        tapp = await models.TelegramApp.objects.filter(id=callback_data.app_id).afirst()
        session, created = await models.TelegramSession.objects.aget_or_create(account=taccount, app=tapp)
        session = Session(session=session)
        client = telethon.TelegramClient(
            session, tapp.api_id, tapp.api_hash, proxy=("http", "172.23.224.1", 10809, True)
        )
        await client.connect()
        is_authed = await client.is_user_authorized()
        if is_authed:
            return message.message.edit_text(gettext("already done"))
        qr_login = await client.qr_login()
        counter = 0
        qr = QRCode()
        reply_to_message_id = message.message.message_id
        while True:
            counter += 1
            qr.clear()
            qr.add_data(qr_login.url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="red", back_color="white")
            img_bytes = io.BytesIO()
            img.save(img_bytes)
            msg = await aiobot.send_photo(
                chat_id=message.message.chat.id,
                photo=BufferedInputFile(file=img_bytes.getvalue(), filename="dummy"),
                caption=gettext("scan this with account @{0}").format(taccount.username) + f"\n{qr_login.url}",
                reply_to_message_id=reply_to_message_id,
            )
            try:
                r = await qr_login.wait()
            except asyncio.TimeoutError as e:
                msg = await msg.reply("\n!! " + gettext("expired, wait for the next"))
                reply_to_message_id = msg.message_id
                await qr_login.recreate()
            except telethon.errors.rpcerrorlist.SessionPasswordNeededError as e:
                await client.sign_in(password=taccount.password)
            except Exception as e:
                await msg.reply(f"error {e}")
                raise e
            else:
                break
        await sync_to_async(session.close)()
        await msg.reply("done")

    else:
        pass
