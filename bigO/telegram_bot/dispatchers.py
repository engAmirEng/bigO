import io
from enum import Enum

from asgiref.sync import sync_to_async

import aiogram.filters.callback_data
import aiogram.methods
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from django.utils.translation import gettext

from . import models
from .router import AppRouter
from .utils import thtml_normalize_markup, thtml_reverse_normalize_markup


async def app_filter_callback(*args, **kwargs):
    return True, args, kwargs


router = AppRouter(name="admin.telegram_bot", app_filter_callback=app_filter_callback)


class MessageForm(StatesGroup):
    message_id = State()


class MessageAction(str, Enum):
    VIEW = "view"
    EDIT = "edit"


class MessageCallbackData(aiogram.filters.callback_data.CallbackData, prefix="messages"):
    message_id: str
    action: MessageAction


class NewMessageCallbackData(aiogram.filters.callback_data.CallbackData, prefix="new_message"):
    pass


@router.message(aiogram.F.text.startswith("to_thtml"))
async def message_menu(
    message: Message,
    tuser: models.TelegramUser | None,
    state: FSMContext,
    aiobot: aiogram.Bot,
    bot_obj: models.TelegramBot,
) -> aiogram.methods.TelegramMethod | None:
    await state.set_state(state=None)
    if tuser is None or tuser.user is None:
        return message.answer("401")
    if not tuser.user.is_superuser:
        return message.answer("403")
    res = thtml_reverse_normalize_markup(message.html_text)
    return message.reply_document(document=BufferedInputFile(file=res.encode("utf-8"), filename="thtml_message.txt"))


@router.message(aiogram.F.caption.startswith("from_thtml"))
async def message_menu(
    message: Message,
    tuser: models.TelegramUser | None,
    state: FSMContext,
    aiobot: aiogram.Bot,
    bot_obj: models.TelegramBot,
) -> aiogram.methods.TelegramMethod | None:
    await state.set_state(state=None)
    if tuser is None or tuser.user is None:
        return message.answer("401")
    if not tuser.user.is_superuser:
        return message.answer("403")
    if message.document is None:
        return message.answer("no doc")
    if message.document.file_size > 1 * 1024 * 1024:
        return message.answer("file too large")
    bytes_io = io.BytesIO()
    await aiobot.download(file=message.document, destination=bytes_io)

    res = thtml_normalize_markup(bytes_io.getvalue().decode("utf-8"))
    return message.reply(text=res)


@router.message(aiogram.filters.Command("messages"))
async def message_menu(
    message: Message,
    tuser: models.TelegramUser | None,
    state: FSMContext,
    aiobot: aiogram.Bot,
    bot_obj: models.TelegramBot,
) -> aiogram.methods.TelegramMethod | None:
    await state.set_state(state=None)
    if tuser is None or tuser.user is None:
        return message.answer("401")
    if not tuser.user.is_superuser:
        return message.answer("403")
    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.row(
        InlineKeyboardButton(text="new", callback_data=NewMessageCallbackData().pack()),
    )
    async for i in models.TelegramMessage.objects.all()[:20]:
        ikbuilder.row(
            InlineKeyboardButton(text=f"{i.id}", callback_data="dummy"),
            InlineKeyboardButton(
                text="view", callback_data=MessageCallbackData(message_id=str(i.id), action=MessageAction.VIEW).pack()
            ),
        )

    return message.answer(gettext("here"), reply_markup=ikbuilder.as_markup())


@router.callback_query(MessageCallbackData.filter(aiogram.F.action == MessageAction.VIEW))
async def view_message(
    message: CallbackQuery,
    callback_data: MessageCallbackData,
    tuser: models.TelegramUser | None,
    state: FSMContext,
    aiobot: aiogram.Bot,
    bot_obj: models.TelegramBot,
) -> aiogram.methods.TelegramMethod | None:
    if tuser is None or tuser.user is None:
        return message.answer("401")
    user = tuser.user
    if not user.is_superuser:
        return message.answer("403")
    message_obj = (
        await models.TelegramMessage.objects.filter(id=callback_data.message_id).select_related_all_entities().afirst()
    )
    method_name, kw = await message_obj.to_aio_params()
    await getattr(aiobot, method_name)(chat_id=message.message.chat.id, **kw)


@router.callback_query(NewMessageCallbackData.filter())
async def new_message(
    message: CallbackQuery,
    callback_data: MessageCallbackData,
    tuser: models.TelegramUser | None,
    state: FSMContext,
    aiobot: aiogram.Bot,
    bot_obj: models.TelegramBot,
) -> aiogram.methods.TelegramMethod | None:
    if tuser is None or tuser.user is None:
        return message.answer("401")
    user = tuser.user
    if not user.is_superuser:
        return message.answer("403")
    await state.set_state(MessageForm.message_id)
    return message.message.answer(gettext("send it"))


@router.message(MessageForm.message_id)
async def new_message_send(
    message: Message,
    tuser: models.TelegramUser | None,
    state: FSMContext,
    aiobot: aiogram.Bot,
    bot_obj: models.TelegramBot,
) -> aiogram.methods.TelegramMethod | None:
    if tuser is None or tuser.user is None:
        return message.answer("401")
    user = tuser.user
    if not user.is_superuser:
        return message.answer("403")
    message_obj: models.TelegramMessage = await sync_to_async(models.TelegramMessage.from_aio)(
        tmessage=message, sent_by=user, bot=bot_obj
    )
    await state.set_state(state=None)
    method_name, kw = await message_obj.to_aio_params()
    await getattr(aiobot, method_name)(chat_id=message.chat.id, **kw)
