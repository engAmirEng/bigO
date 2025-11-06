from enum import Enum
from typing import Optional

import aiogram.utils.deep_linking
from aiogram import Bot
from aiogram.filters import CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    KeyboardButtonRequestChat,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton, ReplyKeyboardBuilder
from bigO.proxy_manager import models as proxy_manager_models
from bigO.telegram_bot.dispatchers import AppRouter
from bigO.telegram_bot.models import TelegramBot, TelegramUser
from django.template.loader import render_to_string
from django.utils.translation import gettext

from .. import models


async def app_filter_callback(*args, **kwargs):
    bot_obj: TelegramBot | None = kwargs.get("bot_obj")
    if bot_obj is None:
        return False, args, kwargs
    try:
        panel_obj = await models.Panel.objects.select_related("agency").aget(bot=bot_obj, is_active=True)
    except models.Panel.DoesNotExist:
        return False, args, kwargs
    return True, args, {**kwargs, "panel_obj": panel_obj}


router = AppRouter(name="teleport", app_filter_callback=app_filter_callback)


class SimpleButtonName(str, Enum):
    MENU = "menu"
    NEW_ACCOUNT_ME = "new_account_me"


class SimpleButtonCallbackData(CallbackData, prefix="simplebutton"):
    button_name: SimpleButtonName


class AgentAgencyAction(str, Enum):
    OVERVIEW = "overview"
    NEW_PROFILE = "new_profile"


class AgentAgencyCallbackData(CallbackData, prefix="agent_agency"):
    pk: int
    action: AgentAgencyAction


class MemberAgencyAction(str, Enum):
    OVERVIEW = "overview"
    LIST_AVAILABLE_PLANS = "list_available_plans"


class MemberAgencyCallbackData(CallbackData, prefix="member_agency"):
    agency_id: int
    action: MemberAgencyAction


@router.callback_query(SimpleButtonCallbackData.filter(aiogram.F.button_name == SimpleButtonName.MENU))
@router.message(CommandStart(magic=~aiogram.F.args))
async def menu_handler(
    message: CallbackQuery | Message,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()

    ikbuilder = InlineKeyboardBuilder()
    agency = panel_obj.agency
    if tuser is None or tuser.user is None:
        text = gettext("برای استفاده از خدمات ما از معرف خود لینک معرفی دریافت کنید.")
        if isinstance(message, Message):
            return message.answer(text, reply_markup=ikbuilder.as_markup())
        else:
            return message.message.edit_text(text)
    user = tuser.user
    try:
        agent = await proxy_manager_models.Agent.objects.aget(user=tuser.user, agency=agency)
    except proxy_manager_models.Agent.DoesNotExist:
        agent = None

    if agent:
        ikbuilder.row(
            InlineKeyboardButton(
                text=gettext("مدیریت"),
                callback_data=AgentAgencyCallbackData(pk=agent.agency_id, action=AgentAgencyAction.OVERVIEW).pack(),
            ),
            InlineKeyboardButton(
                text=gettext("اکانت جدید"),
                callback_data=AgentAgencyCallbackData(pk=agency.id, action=AgentAgencyAction.NEW_PROFILE).pack(),
            ),
            InlineKeyboardButton(text=gettext("مدیریت اکانت ها"), switch_inline_query_current_chat="profiles manage "),
        )

        ikbuilder.row(
            InlineKeyboardButton(text=gettext("ارسال به کاربر"), switch_inline_query="profiles status "),
        )

        text = render_to_string("teleport/agent/start.thtml", context={"agency": agency})
    else:
        text = gettext("دریافت اکانت جدید")
        ikbuilder.row(
            InlineKeyboardButton(
                text=text,
                callback_data=MemberAgencyCallbackData(
                    agency_id=agency.id, action=MemberAgencyAction.LIST_AVAILABLE_PLANS
                ).pack(),
            ),
        )
        subscriptionprofile_qs = (
            proxy_manager_models.SubscriptionProfile.objects.filter(user=user, initial_agency=agency)
            .ann_last_usage_at()
            .ann_last_sublink_at()
            .ann_current_period_fields()
            .filter(current_created_at__isnull=False)
            .order_by("-current_created_at")
        )

        subscriptionprofiles = [i async for i in subscriptionprofile_qs]
        text = render_to_string(
            "teleport/member/start.thtml", context={"agency": agency, "subscriptionprofiles": subscriptionprofiles}
        )
    if isinstance(message, Message):
        return message.answer(text, reply_markup=ikbuilder.as_markup())
    else:
        return message.message.edit_text(text, reply_markup=ikbuilder.as_markup())
