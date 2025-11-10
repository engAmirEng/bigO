import asyncio
import re
from enum import Enum
from typing import Optional

import sentry_sdk
from asgiref.sync import sync_to_async

import aiogram.exceptions
import aiogram.utils.deep_linking
import bigO.utils.models
from aiogram import Bot
from aiogram.filters import CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
from bigO.proxy_manager import services as proxy_manager_services
from bigO.telegram_bot.dispatchers import AppRouter
from bigO.telegram_bot.models import TelegramBot, TelegramUser
from bigO.telegram_bot.utils import thtml_render_to_string
from bigO.users.models import User
from django.db.models import Exists, OuterRef, Q
from django.http import QueryDict
from django.utils import timezone
from django.utils.translation import gettext

from ....proxy_manager.subscription.planproviders import TypeSimpleDynamic1, TypeSimpleStrict1
from ....users.models import User
from ... import models, services
from ..base import AgentAgencyAction, AgentAgencyCallbackData, SimpleButtonCallbackData, SimpleButtonName, router
from ..utils import (
    MASTER_PATH_FILTERS,
    SUB_OWNER_PATH_FILTERS,
    MasterBotFilter,
    QueryPathName,
    StartCommandQueryFilter,
    get_dispatch_query,
    query_magic_dispatcher,
)


class AgentAgencyPlanAction(str, Enum):
    NEW_PROFILE = "new_profile"


class AgentAgencyPlanCallbackData(CallbackData, prefix="agent_agency"):
    pk: int
    plan_id: int
    action: AgentAgencyPlanAction


class AgentAgencyProfileAction(str, Enum):
    RENEW = "renew"


class AgentAgencyProfileCallbackData(CallbackData, prefix="agent_agency"):
    profile_id: int
    action: AgentAgencyProfileAction


@router.inline_query(aiogram.F.query.startswith("profiles manage "))
async def inline_profiles_startlink_handler(
    inline_query: InlineQuery,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
):
    query = inline_query.query.removeprefix("profiles manage ").strip().lower()
    agency = panel_obj.agency
    try:
        agent_obj = await proxy_manager_models.Agent.objects.select_related("agency").aget(
            user=tuser.user, agency=agency, is_active=True
        )
    except proxy_manager_models.Agent.DoesNotExist:
        return

    subprofiles_qs = (
        proxy_manager_services.get_agent_current_subscriptionprofiled_qs(agent=agent_obj)
        .filter(
            bigO.utils.models.get_search_q(
                query=query, fields=["title", "uuid", "xray_uuid", "description", "user__name", "user__username"]
            )
        )
        .select_related("initial_agency", "user")
        .ann_last_usage_at()
        .ann_last_sublink_at()
        .ann_current_period_fields()
    )

    results = []
    async for subscriptionprofile_obj in subprofiles_qs[:50]:
        ikbuilder = InlineKeyboardBuilder()
        ikbuilder.button(
            text=gettext("تمدید"),
            callback_data=AgentAgencyProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=AgentAgencyProfileAction.RENEW
            ),
        )
        ikbuilder.button(
            text=gettext("مشاهده منو"),
            callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.MENU),
        )
        msg = ""
        text = thtml_render_to_string(
            "teleport/member/subscription_profile_startlink.thtml",
            context={"msg": msg, "subscriptionprofile": subscriptionprofile_obj},
        )
        results.append(
            InlineQueryResultArticle(
                id=f"{subscriptionprofile_obj.id}",
                title=str(subscriptionprofile_obj),
                description=subscriptionprofile_obj.description,
                input_message_content=InputTextMessageContent(message_text=text),
                reply_markup=ikbuilder.as_markup(),
            )
        )
    return inline_query.answer(results=results, is_personal=True, cache_time=0)


@router.inline_query(aiogram.F.query.startswith("users startlink "))
async def inline_users_startlink_handler(
    inline_query: InlineQuery,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
):
    query = inline_query.query.removeprefix("users startlink ").strip().lower()
    agency = panel_obj.agency
    user = tuser and tuser.user
    if not (user and tuser.user.is_superuser):
        return

    users_qs = User.objects.filter(bigO.utils.models.get_search_q(query=query, fields=["name", "username"]))

    results = []
    async for user_obj in users_qs[:50]:
        startlink = services.get_user_startlink(bot_obj=bot_obj, user=user_obj)
        text = gettext("جهت اتصال به کاربر خود از طریق این لینک وارد ربات شوید") + "\n" + startlink
        results.append(
            InlineQueryResultArticle(
                id=f"{user.id}",
                title=f"startlink for {str(user)}",
                input_message_content=InputTextMessageContent(message_text=text),
            )
        )
    return inline_query.answer(results=results, is_personal=True, cache_time=0)


@router.inline_query(aiogram.F.query.startswith("profiles status "))
async def inline_profiles_startlink_handler(
    inline_query: InlineQuery,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
):
    query = inline_query.query.removeprefix("profiles status ").strip().lower()
    agency = panel_obj.agency
    try:
        agent_obj = await proxy_manager_models.Agent.objects.select_related("agency").aget(
            user=tuser.user, agency=agency, is_active=True
        )
    except proxy_manager_models.Agent.DoesNotExist:
        return

    subprofiles_qs = (
        proxy_manager_services.get_agent_current_subscriptionprofiled_qs(agent=agent_obj)
        .filter(
            bigO.utils.models.get_search_q(
                query=query, fields=["title", "uuid", "xray_uuid", "description", "user__name", "user__username"]
            )
        )
        .select_related("initial_agency", "user")
        .ann_last_usage_at()
        .ann_last_sublink_at()
        .ann_current_period_fields()
    )

    results = []

    async for subscriptionprofile_obj in subprofiles_qs[:50]:
        startlink = services.get_subscription_profile_startlink(
            bot_obj=bot_obj, subscription_profile=subscriptionprofile_obj
        )
        connect_text = gettext("جهت اتصال به اکانت خود از طریق این لینک وارد ربات شوید") + "\n" + startlink
        msg = ""
        text = thtml_render_to_string(
            "teleport/member/subscription_profile_startlink.thtml",
            context={"msg": msg, "subscriptionprofile": subscriptionprofile_obj},
        )
        text += connect_text

        ikbuilder = InlineKeyboardBuilder()
        normal_sublink = await sync_to_async(subscriptionprofile_obj.get_sublink)()
        ikbuilder.row(
            InlineKeyboardButton(
                text=gettext("کپی لینک اشتراک اندروید"),
                copy_text=CopyTextButton(text=normal_sublink),
            ),
            InlineKeyboardButton(
                text=gettext("کپی لینک اشتراک ios"),
                copy_text=CopyTextButton(text=normal_sublink + "?base64=true"),
            ),
        )
        results.append(
            InlineQueryResultArticle(
                id=f"{subscriptionprofile_obj.id}",
                title=str(subscriptionprofile_obj),
                description=gettext("نمایش پروفایل اشتراک") + "\n" + subscriptionprofile_obj.description,
                input_message_content=InputTextMessageContent(message_text=text),
                reply_markup=ikbuilder.as_markup(),
            )
        )
    return inline_query.answer(results=results, is_personal=True, cache_time=0)


@router.message(aiogram.F.text.startswith("manage profile "))
async def agent_manage_profile_handler(
    message: Message,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()
    profile_uuid_res = re.search(r"manage profile (?P<profile_uuid_res>[0-9a-f:]{32})", message.text)
    profile_uuid = profile_uuid_res.group("profile_uuid_res")
    if profile_uuid is None:
        return message.reply(gettext("معتبر نیست"))
    agency = panel_obj.agency
    try:
        agent_obj = await proxy_manager_models.Agent.objects.select_related("agency").aget(
            user=tuser.user, agency=agency, is_active=True
        )
    except proxy_manager_models.Agent.DoesNotExist:
        return
    try:
        subscriptionprofile_obj = (
            await proxy_manager_services.get_agent_current_subscriptionprofiled_qs(agent=agent_obj)
            .select_related("initial_agency", "user")
            .ann_last_usage_at()
            .ann_last_sublink_at()
            .ann_current_period_fields()
            .filter(current_created_at__isnull=False)
            .aget(uuid=profile_uuid)
        )
    except proxy_manager_models.SubscriptionProfile.DoesNotExist:
        return message.reply(gettext("پیدا نشد."))
    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.button(
        text=gettext("تمدید"),
        callback_data=AgentAgencyProfileCallbackData(
            profile_id=subscriptionprofile_obj.id, action=AgentAgencyProfileAction.RENEW
        ),
    )
    ikbuilder.button(
        text=gettext("مشاهده منو"),
        callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.MENU),
    )
    msg = gettext("خدمت شما")
    text = thtml_render_to_string(
        "teleport/member/subscription_profile_startlink.thtml",
        context={"msg": msg, "subscriptionprofile": subscriptionprofile_obj},
    )

    return message.reply(text, reply_markup=ikbuilder.as_markup())
