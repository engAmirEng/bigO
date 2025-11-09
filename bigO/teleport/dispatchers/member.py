import asyncio
from enum import Enum
from typing import Optional

import sentry_sdk
from asgiref.sync import sync_to_async

import aiogram.exceptions
import aiogram.utils.deep_linking
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
from bigO.users.models import User
from django.db.models import Exists, OuterRef, Q
from django.http import QueryDict
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext

from ...proxy_manager.subscription.planproviders import TypeSimpleDynamic1, TypeSimpleStrict1
from ...users.models import User
from .. import models, services
from .base import (
    MemberAgencyAction,
    MemberAgencyCallbackData,
    ProfileAction,
    ProfileCallbackData,
    SimpleButtonCallbackData,
    SimpleButtonName,
    router,
)
from .utils import (
    MASTER_PATH_FILTERS,
    SUB_OWNER_PATH_FILTERS,
    MasterBotFilter,
    QueryPathName,
    StartCommandQueryFilter,
    get_dispatch_query,
    query_magic_dispatcher,
)


class MemberAgencyPlanAction(str, Enum):
    NEW_PROFILE = "new_profile"


class MemberAgencyPlanCallbackData(CallbackData, prefix="member_agency"):
    agency_id: int
    plan_id: int
    action: MemberAgencyPlanAction


@router.callback_query(MemberAgencyCallbackData.filter(aiogram.F.action == MemberAgencyAction.LIST_AVAILABLE_PLANS))
async def new_profile_me_handler(
    message: CallbackQuery,
    callback_data: MemberAgencyCallbackData,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()
    agency = panel_obj.agency
    useragency = await proxy_manager_models.AgencyUser.objects.filter(
        user=tuser.user, agency=agency, agency_id=callback_data.agency_id
    ).afirst()
    if useragency is None:
        return message.message.edit_text(gettext("تغییری ایجاد شده، ار ابتدا اقدام کنید."))

    # sub_qs = proxy_manager_models.AgencyPlanSpec.objects.filter(agency=useragency.agency, capacity__gt=0, plan=OuterRef("id"))
    agencyusergroupplanspec_qs = proxy_manager_services.get_user_available_plans(
        user=useragency.user, agency=useragency.agency
    )
    agencyusergroupplanspecs = [i async for i in agencyusergroupplanspec_qs]
    ikbuilder = InlineKeyboardBuilder()
    for agencyusergroupplanspec in agencyusergroupplanspecs:
        ikbuilder.button(
            text=agencyusergroupplanspec.plan.name,
            callback_data=MemberAgencyPlanCallbackData(
                agency_id=useragency.agency_id,
                plan_id=agencyusergroupplanspec.plan.id,
                action=MemberAgencyPlanAction.NEW_PROFILE,
            ),
        )
    text = render_to_string(
        "teleport/member/availbale_plans_new_profile.thtml",
        context={"agencyusergroupplanspecs": agencyusergroupplanspecs},
    )
    return message.message.edit_text(text=text, reply_markup=ikbuilder.as_markup())


@router.message(StartCommandQueryFilter(query_magic=query_magic_dispatcher(QueryPathName.ASSOCIATE_TO_USER)))
async def user_startlink_handler(
    message: Message,
    command_query: QueryDict,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()
    user = tuser and tuser.user
    secret_key = command_query.get("k")
    if not secret_key:
        return
    data = await services.get_secret_key(secret_key=secret_key)
    if not data or not (to_user_id := data.get("user_id")):
        return message.reply_to_message(gettext("شناسایی نشد"))
    to_user_obj = await User.objects.get(id=to_user_id)
    transfer_ownership: bool = data.get("transfer_ownership")
    referred_by = None
    if not user:
        tuser.user = to_user_obj
        tuser.save()
    else:
        if transfer_ownership:
            tuser.user = tuser
            tuser.save()
        else:
            return message.reply(gettext("شما از قبل به {0} متصل هستید").format(str(user)))
    return message.reply(gettext("به {0} متصل شدید").format(str(to_user_obj)))


@router.message(StartCommandQueryFilter(query_magic=query_magic_dispatcher(QueryPathName.ASSOCIATE_TO_ACCOUNT)))
async def subscription_profile_startlink_handler(
    message: Message,
    command_query: QueryDict,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()
    user = tuser and tuser.user
    agency = panel_obj.agency
    secret_key = command_query.get("k")
    if not secret_key:
        return
    data = await services.get_secret_key(secret_key=secret_key)
    if not data or not (subscription_profile_id := data.get("subscription_profile_id")):
        return message.reply_to_message(gettext("شناسایی نشد"))

    subscriptionprofile_obj = (
        await proxy_manager_models.SubscriptionProfile.objects.filter(id=subscription_profile_id)
        .select_related("initial_agency", "user")
        .ann_last_usage_at()
        .ann_last_sublink_at()
        .ann_current_period_fields()
        .filter(current_created_at__isnull=False)
        .aget()
    )
    transfer_ownership: bool = data.get("transfer_ownership")
    referred_by = None
    if not user:
        if transfer_ownership:
            user = None
        else:
            user = subscriptionprofile_obj.user
        if user is None:
            user = User()
            user.name = message.from_user.full_name
            user.username = await services.make_username(base=message.from_user.username)
        await user.asave()
        if tuser is None:
            tuser = TelegramUser()
            tuser.user = user
            tuser.tid = message.from_user.id
            tuser.bot = bot_obj
        else:
            tuser.user = user
        await tuser.asave()

    if subscriptionprofile_obj.user is None:
        if user:
            subscriptionprofile_obj.user = user
            await subscriptionprofile_obj.asave()
        else:
            user = User()
            user.name = message.from_user.full_name
            user.username = await services.make_username(base=message.from_user.username)
            tuser.user = user
            await user.asave()
            await tuser.asave()
        msg = gettext("مالکیت اکانت {0} به شما({1}) منتقل شد.").format(str(subscriptionprofile_obj), str(user))
    else:
        if user:
            if subscriptionprofile_obj.user != user:
                if transfer_ownership:
                    try:
                        referred_by = await proxy_manager_models.AgencyUser.objects.aget(
                            user=subscriptionprofile_obj.user, agency=agency
                        )
                    except proxy_manager_models.AgencyUser.DoesNotExist:
                        pass
                    subscriptionprofile_obj.user = user
                    await subscriptionprofile_obj.asave()
                    msg = gettext("مالکیت اکانت {0} از {1} به شما({2}) منتقل شد.").format(
                        str(subscriptionprofile_obj), str(referred_by), str(user)
                    )
                else:
                    msg = gettext("مالکیت اکانت {0} از قبل به دیگری اختصاص یافته.").format(
                        str(subscriptionprofile_obj)
                    )
            else:
                msg = gettext("از قبل به اکانت خود متصل بودید.")
        else:
            if subscriptionprofile_obj.user:
                tuser.user = subscriptionprofile_obj.user
                await tuser.asave()
                msg = gettext("مالکیت اکانت {0} به شما({2}) منتقل شد.").format(str(subscriptionprofile_obj), str(user))
            else:
                user = User()
                user.name = message.from_user.full_name
                user.username = await services.make_username(base=message.from_user.username)
                tuser.user = user
                subscriptionprofile_obj.user = user
                await user.asave()
                await tuser.asave()
                await subscriptionprofile_obj.asave()
                msg = gettext("مالکیت اکانت {0} به شما({2}) منتقل شد.").format(str(subscriptionprofile_obj), str(user))
    agencyuser, created = await proxy_manager_models.AgencyUser.objects.aget_or_create(
        user=tuser.user, agency=subscriptionprofile_obj.initial_agency
    )
    if created and referred_by:
        referral_obj = proxy_manager_models.Referral()
        referral_obj.referrer = referred_by
        referral_obj.referee = agencyuser

    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.button(
        text=gettext("مشاهده منو"),
        callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.MENU),
    )
    # ikbuilder.button(
    #     text=gettext("مشاهده منو"),
    #     callback_data=ContentCallbackData(pk=subscriptionprofile_obj.pk, action=SubscriptionProfileAction.GET_LINK),
    # )
    text = render_to_string(
        "teleport/member/subscription_profile_startlink.thtml",
        context={"msg": msg, "subscriptionprofile": subscriptionprofile_obj},
    )

    return message.answer(text, reply_markup=ikbuilder.as_markup())


@router.callback_query(ProfileCallbackData.filter(aiogram.F.action == ProfileAction.DETAIL))
async def my_accounts_handler(
    message: CallbackQuery,
    callback_data: ProfileCallbackData,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()

    agency = panel_obj.agency
    if tuser is None or tuser.user is None:
        text = gettext("برای استفاده از خدمات ما از معرف خود لینک معرفی دریافت کنید.")
        return message.answer(text, show_alert=True)
    user = tuser.user
    try:
        subscriptionprofile_obj = await (
            proxy_manager_models.SubscriptionProfile.objects.filter(user=user, initial_agency=agency)
            .ann_last_usage_at()
            .ann_last_sublink_at()
            .ann_current_period_fields()
            .filter(current_created_at__isnull=False)
            .order_by("-current_created_at")
        ).aget(id=callback_data.profile_id)
    except proxy_manager_models.SubscriptionProfile.DoesNotExist:
        return message.answer(gettext("اکانت یافت نشد."))

    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔙 " + gettext("بازکشت به منو"),
            callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.MENU).pack(),
        ),
        InlineKeyboardButton(
            text="🔄 Refresh",
            callback_data=ProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=ProfileAction.DETAIL
            ).pack(),
        ),
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text=gettext("شارژ این اکانت"),
            callback_data=ProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=ProfileAction.RENEW
            ).pack(),
        ),
    )
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

    text = render_to_string(
        "teleport/member/subscription_profile_startlink.thtml",
        context={"msg": "", "subscriptionprofile": subscriptionprofile_obj},
    )
    return message.message.edit_text(text, reply_markup=ikbuilder.as_markup())
