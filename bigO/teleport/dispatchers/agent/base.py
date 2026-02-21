import re
from enum import Enum
from typing import Optional

from asgiref.sync import sync_to_async

import aiogram.utils.deep_linking
import bigO.utils.models
from aiogram import Bot
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    CopyTextButton,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton, ReplyKeyboardBuilder
from bigO.proxy_manager import models as proxy_manager_models
from bigO.proxy_manager import services as proxy_manager_services
from bigO.telegram_bot import models as telegram_bot_models
from bigO.telegram_bot.models import TelegramBot, TelegramUser
from bigO.telegram_bot.utils import thtml_render_to_string
from django.http import QueryDict
from django.utils.translation import gettext

from ....users.models import User
from ... import models, services
from ...types import SimpleButtonCallbackData, SimpleButtonName
from ..base import router
from ..utils import QueryPathName, StartCommandQueryFilter, query_magic_dispatcher


class AgentAgencyPlanAction(str, Enum):
    NEW_PROFILE = "new_profile"


class AgentAgencyPlanCallbackData(CallbackData, prefix="agent_agency"):
    pk: int
    plan_id: int
    action: AgentAgencyPlanAction


class AgentAgencyProfileAction(str, Enum):
    RENEW = "renew"
    DETAIL = "detail"
    SEE_PROXY_LIST = "SEE_PROXY_LIST"


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
        text = f"manage profile {subscriptionprofile_obj.uuid.hex}"
        results.append(
            InlineQueryResultArticle(
                id=f"{subscriptionprofile_obj.id}",
                title=str(subscriptionprofile_obj),
                description=subscriptionprofile_obj.description,
                input_message_content=InputTextMessageContent(message_text=text),
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
        connect_text = gettext("جهت مدیریت اکانت خود (تمدید، شارژ و...) از طریق دکمه 'ورود به ربات' وارد شوید.")
        text = await thtml_render_to_string(
            "teleport/member/subscription_profile_overview.thtml",
            context={"state": None, "subscriptionprofile": subscriptionprofile_obj},
        )
        text += "\n" + connect_text

        ikbuilder = InlineKeyboardBuilder()
        normal_sublink = await sync_to_async(subscriptionprofile_obj.get_sublink)()
        ikbuilder.row(
            InlineKeyboardButton(
                text="🔗 " + gettext("ورود به ربات"),
                url=startlink,
            )
        )
        ikbuilder.row(
            InlineKeyboardButton(
                text="⚿ " + gettext("لینک ساب اندروید"),
                copy_text=CopyTextButton(text=normal_sublink),
            ),
            InlineKeyboardButton(
                text="⚿ " + gettext("لینک ساب ios"),
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
@router.message(StartCommandQueryFilter(query_magic=query_magic_dispatcher(QueryPathName.ADMIN_PROFILE_DETAIL)))
@router.callback_query(AgentAgencyProfileCallbackData.filter(aiogram.F.action == AgentAgencyProfileAction.DETAIL))
async def agent_manage_profile_handler(
    message: Message | CallbackQuery,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
    command_query: QueryDict | None = None,
    callback_data: AgentAgencyProfileCallbackData | None = None,
) -> Optional[aiogram.methods.TelegramMethod]:
    profile_id = None
    profile_uuid = None
    if command_query:
        profile_id = command_query["id"]
    elif callback_data:
        profile_id = callback_data.profile_id
    else:
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
        subscriptionprofile_qs = (
            proxy_manager_services.get_agent_current_subscriptionprofiled_qs(agent=agent_obj)
            .select_related("initial_agency", "user")
            .ann_last_usage_at()
            .ann_last_sublink_at()
            .ann_current_period_fields()
        )
        if profile_uuid:
            subscriptionprofile_obj = await subscriptionprofile_qs.aget(uuid=profile_uuid)
        else:
            subscriptionprofile_obj = await subscriptionprofile_qs.aget(id=profile_id)
        subscriptionprofile_obj: proxy_manager_models.SubscriptionProfile
    except proxy_manager_models.SubscriptionProfile.DoesNotExist:
        return message.reply(gettext("پیدا نشد."))
    all_user_accounts_list = []
    if subscriptionprofile_obj.user:
        all_user_accounts_list = [
            i
            async for i in proxy_manager_services.get_agent_current_subscriptionprofiled_qs(agent=agent_obj).filter(
                user=subscriptionprofile_obj.user
            )
        ]
    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔙 " + gettext("بازکشت به منو"),
            callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.MENU).pack(),
        ),
        InlineKeyboardButton(
            text="🔄 Refresh",
            callback_data=AgentAgencyProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=AgentAgencyProfileAction.DETAIL
            ).pack(),
        ),
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text="💳 " + gettext("تمدید"),
            callback_data=AgentAgencyProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=AgentAgencyProfileAction.RENEW
            ).pack(),
        )
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text="📑 " + gettext("پروکسی ها"),
            callback_data=AgentAgencyProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=AgentAgencyProfileAction.SEE_PROXY_LIST
            ).pack(),
        ),
    )
    normal_sublink = await sync_to_async(subscriptionprofile_obj.get_sublink)()
    ikbuilder.row(
        InlineKeyboardButton(
            text="⚿ " + gettext("لینک ساب اندروید"),
            copy_text=CopyTextButton(text=normal_sublink),
        ),
        InlineKeyboardButton(
            text="⚿ " + gettext("لینک ساب ios"),
            copy_text=CopyTextButton(text=normal_sublink + "?base64=true"),
        ),
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text=gettext("ارسال به کاربر"), switch_inline_query=f"profiles status {subscriptionprofile_obj.uuid}"
        ),
    )
    if len(all_user_accounts_list) > 1:
        ikbuilder.row(
            InlineKeyboardButton(
                text=gettext("اکانت های دیگر این کاربر") + " 👇",
                callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.DISPLAY_PLACEHOLDER).pack(),
            )
        )
        ikbuilder_all_user_accounts = InlineKeyboardBuilder()
        for i in all_user_accounts_list:
            ikbuilder_all_user_accounts.button(
                text=("✅" if (i == subscriptionprofile_obj) else "") + await sync_to_async(str)(i),
                callback_data=AgentAgencyProfileCallbackData(
                    profile_id=i.id, action=AgentAgencyProfileAction.DETAIL
                ).pack(),
            )
        ikbuilder_all_user_accounts.adjust(3, repeat=True)
        ikbuilder.attach(ikbuilder_all_user_accounts)
    if subscriptionprofile_obj.user:
        profile_tuser = await telegram_bot_models.TelegramUser.objects.filter(
            bot=bot_obj, user=subscriptionprofile_obj.user
        ).afirst()
    else:
        profile_tuser = None

    text = await thtml_render_to_string(
        "teleport/agent/subscription_profile_overview.thtml",
        context={"state": state, "subscriptionprofile": subscriptionprofile_obj, "profile_tuser": profile_tuser},
    )
    if isinstance(message, Message):
        return message.reply(text, reply_markup=ikbuilder.as_markup())
    else:
        return message.message.edit_text(text, reply_markup=ikbuilder.as_markup())


@router.callback_query(
    AgentAgencyProfileCallbackData.filter(aiogram.F.action == AgentAgencyProfileAction.SEE_PROXY_LIST)
)
async def member_see_toturial_content_handler(
    message: CallbackQuery,
    callback_data: AgentAgencyProfileCallbackData,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    agency = panel_obj.agency
    try:
        agent_obj = await proxy_manager_models.Agent.objects.select_related("agency").aget(
            user=tuser.user, agency=agency, is_active=True
        )
    except proxy_manager_models.Agent.DoesNotExist:
        return
    try:
        subscriptionprofile_obj = await proxy_manager_services.get_agent_current_subscriptionprofiled_qs(
            agent=agent_obj
        ).aget(id=callback_data.profile_id)
    except proxy_manager_models.SubscriptionProfile.DoesNotExist:
        return message.reply(gettext("پیدا نشد."))

    subscriptionperiod_obj = (
        await subscriptionprofile_obj.periods.filter(selected_as_current=True)
        .select_related("plan__connection_rule")
        .ann_expires_at()
        .ann_up_bytes_remained()
        .ann_dl_bytes_remained()
        .ann_total_limit_bytes()
        .afirst()
    )
    if subscriptionperiod_obj is None:
        text = gettext("این اکانت فعال نیست")
    else:
        res_lines = await proxy_manager_services.get_profile_proxies(subscriptionperiod_obj=subscriptionperiod_obj)
        text = ""
        for line in res_lines:
            text += f"<code>{line}</code>"

    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔄 Refresh",
            callback_data=AgentAgencyProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=AgentAgencyProfileAction.SEE_PROXY_LIST
            ).pack(),
        ),
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔙 " + gettext("بازگشت "),
            callback_data=AgentAgencyProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=AgentAgencyProfileAction.DETAIL
            ).pack(),
        )
    )
    await message.answer()
    return message.message.edit_text(text=text, reply_markup=ikbuilder.as_markup())
