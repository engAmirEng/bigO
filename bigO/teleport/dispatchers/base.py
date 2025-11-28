import functools
from enum import Enum
from typing import Optional

import makefun

import aiogram.utils.deep_linking
from aiogram import Bot
from aiogram.filters import CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    CopyTextButton,
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
from bigO.telegram_bot.utils import thtml_render_to_string
from django.utils.translation import gettext

from .. import models, services


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
    DISPLAY_PLACEHOLDER = "display_placeholder"


class SimpleButtonCallbackData(CallbackData, prefix="simplebutton"):
    button_name: SimpleButtonName


class SimpleBoolCallbackData(CallbackData, prefix="simplebool"):
    result: bool


class AgentAgencyAction(str, Enum):
    OVERVIEW = "overview"
    TO_MEMBER_PANEL = "to_member_panel"
    TO_AGENT_PANEL = "to_agent_panel"
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


class MemberAgencyProfileAction(str, Enum):
    DETAIL = "detail"
    LIST_AVAILABLE_PLANS = "list_available_plans"
    PASS_CHANGE = "pass_change"
    TRANSFER_TO_ANOTHER = "transfer_to_another"


class MemberAgencyProfileCallbackData(CallbackData, prefix="profile"):
    profile_id: int
    action: MemberAgencyProfileAction


class MemberBillAction(str, Enum):
    OVERVIEW = "overview"
    CANCEL = "cancel"


class MemberBillCallbackData(CallbackData, prefix="member_init_paybill"):
    bill_id: int
    action: MemberBillAction


def remove_state(fn):
    @makefun.wraps(fn)
    async def wrapper(*args, **kwargs):
        resp = await fn(*args, **kwargs)
        state: FSMContext | None = kwargs.get("state")
        if state:
            await state.set_state(state=None)
        return resp

    return wrapper


@remove_state
@router.callback_query(SimpleButtonCallbackData.filter(aiogram.F.button_name == SimpleButtonName.MENU))
@router.callback_query(AgentAgencyCallbackData.filter(aiogram.F.action == AgentAgencyAction.TO_AGENT_PANEL))
@router.callback_query(AgentAgencyCallbackData.filter(aiogram.F.action == AgentAgencyAction.TO_MEMBER_PANEL))
@router.message(CommandStart(magic=~aiogram.F.args))
async def menu_handler(
    message: CallbackQuery | Message,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
    callback_data: AgentAgencyCallbackData | None = None,
) -> Optional[aiogram.methods.TelegramMethod]:
    agency = panel_obj.agency
    if tuser is None or tuser.user is None:
        text = gettext("برای استفاده از خدمات ما از معرف خود لینک معرفی دریافت کنید.")
        if isinstance(message, Message):
            return message.answer(text)
        else:
            return message.message.edit_text(text)
    sdata = await state.get_data()
    user = tuser.user
    try:
        agent = await proxy_manager_models.Agent.objects.aget(user=tuser.user, agency=agency)
    except proxy_manager_models.Agent.DoesNotExist:
        agent = None
    if isinstance(callback_data, AgentAgencyCallbackData):
        if not agent:
            return message.answer(gettext("دسترسی به این مورد را ندارید"), show_alert=True)
        if callback_data.action == AgentAgencyAction.TO_AGENT_PANEL:
            sdata["member_panel"] = False
            await state.set_data(sdata)
        elif callback_data.action == AgentAgencyAction.TO_MEMBER_PANEL:
            sdata["member_panel"] = True
            await state.set_data(sdata)
    member_panel = bool(sdata.get("member_panel"))
    ikbuilder = InlineKeyboardBuilder()
    if agent and member_panel:
        ikbuilder.row(
            InlineKeyboardButton(
                text="🔘" + gettext("پنل مدیریت") + " 🔀 " + "🟢" + gettext("پنل مشتری"),
                callback_data=AgentAgencyCallbackData(
                    pk=agent.agency_id, action=AgentAgencyAction.TO_AGENT_PANEL
                ).pack(),
            )
        )
    elif agent and not member_panel:
        ikbuilder.row(
            InlineKeyboardButton(
                text="🟢" + gettext("پنل مدیریت") + " 🔀 " + "🔘" + gettext("پنل مشتری"),
                callback_data=AgentAgencyCallbackData(
                    pk=agent.agency_id, action=AgentAgencyAction.TO_MEMBER_PANEL
                ).pack(),
            )
        )

    if agent and not member_panel:
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

        text = await thtml_render_to_string("teleport/agent/start.thtml", context={"agency": agency})
    else:
        useragency = (
            await proxy_manager_models.AgencyUser.objects.filter(user=tuser.user, agency=agency)
            .select_related("user", "agency")
            .afirst()
        )
        if useragency is None:
            if agent:
                useragency = proxy_manager_models.AgencyUser()
                useragency.user = user
                useragency.agency = agency
                await useragency.asave()
            else:
                return message.reply(gettext("تغییری ایجاد شده، ار ابتدا اقدام کنید."))
        referlink = (
            await proxy_manager_models.ReferLink.objects.filter(agency_user=useragency, is_active=True)
            .ann_remainded_cap_count()
            .filter(remainded_cap_count__gt=0)
            .afirst()
        )
        ikbuilder.row(
            InlineKeyboardButton(
                text="🔄 Refresh",
                callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.MENU).pack(),
            ),
        )
        if referlink:
            referlink_btn = InlineKeyboardButton(
                text="👥 " + gettext("لینک معرفی"),
                copy_text=CopyTextButton(text=services.get_referlinklink(bot_obj=bot_obj, referlink=referlink)),
            )
        else:
            txt = "👥 " + gettext("طرفیت معرفی شما به پایان رسیده")
            referlink_btn = InlineKeyboardButton(text=txt, copy_text=CopyTextButton(text=txt))
        ikbuilder.row(
            InlineKeyboardButton(
                text=gettext("دریافت اکانت جدید"),
                callback_data=MemberAgencyCallbackData(
                    agency_id=agency.id, action=MemberAgencyAction.LIST_AVAILABLE_PLANS
                ).pack(),
            ),
            referlink_btn,
        )
        subscriptionprofile_qs = (
            proxy_manager_models.SubscriptionProfile.objects.filter(user=user, initial_agency=agency)
            .ann_last_usage_at()
            .ann_last_sublink_at()
            .ann_current_period_fields()
            .order_by("-current_created_at")
        )

        subscriptionprofiles = [i async for i in subscriptionprofile_qs]
        if subscriptionprofiles:
            ikbuilder.row(
                InlineKeyboardButton(
                    text=gettext("اکانت های شما 👇"),
                    callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.DISPLAY_PLACEHOLDER).pack(),
                ),
            )
            ikbuilder_profiles = InlineKeyboardBuilder()
            btns = []
            for subscriptionprofile in subscriptionprofiles:
                btns.append(
                    InlineKeyboardButton(
                        text=str(subscriptionprofile),
                        callback_data=MemberAgencyProfileCallbackData(
                            profile_id=subscriptionprofile.id, action=MemberAgencyProfileAction.DETAIL
                        ).pack(),
                    ),
                )
            ikbuilder_profiles.add(*btns)
            ikbuilder_profiles.adjust(2, repeat=True)
            ikbuilder.attach(ikbuilder_profiles)
        text = await thtml_render_to_string(
            "teleport/member/start.thtml",
            context={"state": state, "agency": agency, "subscriptionprofiles": subscriptionprofiles},
        )
    if isinstance(message, Message):
        return message.answer(text, reply_markup=ikbuilder.as_markup())
    else:
        return message.message.edit_text(text, reply_markup=ikbuilder.as_markup())
