import asyncio
from enum import Enum
from typing import Optional

from django.db.models import Exists, OuterRef
from django.utils import timezone
from django.utils.translation import gettext
import sentry_sdk
from asgiref.sync import sync_to_async

import aiogram.exceptions
from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ChatMemberUpdated, KeyboardButtonRequestChat, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from django.http import QueryDict
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as __

from ...users.models import User
from bigO.telegram_bot import models
from bigO.telegram_bot.models import TelegramUser
from .utils import (
    MASTER_PATH_FILTERS,
    SUB_OWNER_PATH_FILTERS,
    MasterBotFilter,
    QueryPathName,
    StartCommandQueryFilter,
    get_dispatch_query,
    query_magic_dispatcher,
)
from bigO.proxy_manager import models as proxy_manager_models, services as proxy_manager_services
from bigO.users.models import User
from .. import services
import aiogram.utils.deep_linking

router = Router(name=__name__)

class SimpleButtonCallbackData(CallbackData, prefix="simplebutton"):
    button_name: str

class SimpleButtonName(str, Enum):
    MENU = "menu"
    NEW_ACCOUNT_ME = "new_account_me"

class SubscriptionProfileAction(str, Enum):
    GET_LINK = "get_link"

class SubscriptionProfileCallbackData(CallbackData, prefix="subscriptionprofile"):
    pk: int
    action: SubscriptionProfileAction

class MemberAgencyAction(str, Enum):
    OVERVIEW = "overview"
    LIST_AVAILABLE_PLANS = "list_available_plans"

class MemberAgencyCallbackData(CallbackData, prefix="member_agency"):
    agency_id: int
    action: MemberAgencyAction

class MemberAgencyPlanAction(str, Enum):
    NEW_PROFILE = "new_profile"

class MemberAgencyPlanCallbackData(CallbackData, prefix="member_agency"):
    agency_id: int
    plan_id: int
    action: MemberAgencyPlanAction


class AgentAgencyAction(str, Enum):
    OVERVIEW = "overview"
    NEW_PROFILE = "new_profile"

class AgentAgencyCallbackData(CallbackData, prefix="agent_agency"):
    pk: int
    action: AgentAgencyAction


@router.callback_query(
    SimpleButtonCallbackData.filter(aiogram.F.button_name == SimpleButtonName.MENU)
)
@router.message(CommandStart())
async def menu_handler(
    message: CallbackQuery | Message,
    tuser: TelegramUser | None, state: FSMContext, aiobot: Bot, bot_obj: models.TelegramBot
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()
    if tuser is None:
        text = render_to_string("teleport/subscription_profile_startlink.thtml", context={"subscriptionperiod_obj": subscriptionperiod_obj})
        if isinstance(message, Message):
            return message.answer(text, reply_markup=ikbuilder.as_markup())
        else:
            return message.message.edit_text(text)
    subscriptionprofile_qs = proxy_manager_models.SubscriptionProfile.objects.filter(user=tuser.user, initial_agency__telegrambot=bot_obj)
    subscriptionprofiles = [i async for i in subscriptionprofile_qs]
    agent_qs = await tuser.user.user_agents.filter(is_active=True, agency__telegrambot=bot_obj).select_related("agency")
    agents = [i async for i in agent_qs]

    ikbuilder = InlineKeyboardBuilder()
    if subscriptionprofiles or not agents:
        useragency_qs = proxy_manager_models.AgencyUser.objects.filter(user=tuser.user, agency__telegrambot=bot_obj)
        useragencies = [i async for i in useragency_qs]

        for useragency in useragencies:
            if len(useragencies) > 1:
                text = "خرید اکانت جدید ({0})".format(useragency.agency.name)
            else:
                text = "خرید اکانت جدید"
            ikbuilder.button(
                text=text,
                callback_data=MemberAgencyCallbackData(agency_id=useragency.agency_id, action=MemberAgencyAction.LIST_AVAILABLE_PLANS),
            )
    for agent in agents:
        ikbuilder.button(
            text=gettext("مدیریت {0}").format(agent.agency.name),
            callback_data=AgentAgencyCallbackData(pk=agent.agency_id, action=AgentAgencyAction.OVERVIEW),
        )
        ikbuilder.button(
            text=gettext("اکانت جدید {0}").format(agent.agency.name),
            callback_data=AgentAgencyCallbackData(pk=agent.agency_id, action=AgentAgencyAction.NEW_PROFILE),
        )

    text = render_to_string("teleport/subscription_profile_startlink.thtml", context={"subscriptionperiods": subscriptionperiods})

    return message.answer(text, reply_markup=ikbuilder.as_markup())


@router.callback_query(
    MemberAgencyCallbackData.filter(aiogram.F.action == MemberAgencyAction.LIST_AVAILABLE_PLANS)
)
async def new_profile_me_handler(
    message: CallbackQuery,
    callback_data: MemberAgencyCallbackData,
    tuser: TelegramUser | None, state: FSMContext, aiobot: Bot, bot_obj: models.TelegramBot
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()
    useragency = await proxy_manager_models.AgencyUser.objects.filter(user=tuser.user, agency__telegrambot=bot_obj, agency_id=callback_data.agency_id).afirst()
    if useragency is None:
        return message.message.edit_text(gettext("تغییری ایجاد شده، ار ابتدا اقدام کنید."))

    # sub_qs = proxy_manager_models.AgencyPlanSpec.objects.filter(agency=useragency.agency, capacity__gt=0, plan=OuterRef("id"))
    # subscriptionplan_qs = proxy_manager_models.SubscriptionPlan.objects.filter(Exists(sub_qs))
    # subscriptionplans = [i async for i in subscriptionplan_qs]
    agencyusergroupplanspec_qs = proxy_manager_services.get_user_available_plans(user=useragency.user, agency=useragency.agency)
    agencyusergroupplanspecs = [i async for i in agencyusergroupplanspec_qs]
    ikbuilder = InlineKeyboardBuilder()
    for agencyusergroupplanspec in agencyusergroupplanspecs:
        ikbuilder.button(
            text=agencyusergroupplanspec.plan.name,
            callback_data=MemberAgencyPlanCallbackData(agency_id=useragency.agency_id, plan_id=agencyusergroupplanspec.plan.id, action=MemberAgencyPlanAction.NEW_PROFILE),
        )
    text = render_to_string("teleport/member/availbale_plans_new_profile.thtml", context={"agencyusergroupplanspecs": agencyusergroupplanspecs})
    return message.message.edit_text(text=text, reply_markup=ikbuilder.as_markup())


@router.callback_query(
    AgentAgencyCallbackData.filter(aiogram.F.action == AgentAgencyAction.NEW_PROFILE)
)
async def agency_new_profile_handler(
    message: CallbackQuery,
    callback_data: AgentAgencyCallbackData,
    tuser: TelegramUser | None, state: FSMContext, aiobot: Bot, bot_obj: models.TelegramBot
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()
    agent_qs = await tuser.user.user_agents.filter(is_active=True, agency__telegrambot=bot_obj).select_related("agency")
    agent = agent_qs.filter(agency_id=callback_data.pk).afirst()
    if agent is None:
        return message.message.edit_text("شما به این آژانس دسترسی ندارید.")
    # sub_qs = proxy_manager_models.AgencyPlanSpec.objects.filter(agency=agent.agency, capacity__gt=0, plan=OuterRef("id"))
    # subscriptionplan_qs = proxy_manager_models.SubscriptionPlan.objects.filter(Exists(sub_qs))
    agencyplanspec_qs = proxy_manager_services.get_agent_available_plans(agency=agent.agency)
    agencyplanspecs = [i async for i in agencyplanspec_qs]
    ikbuilder = InlineKeyboardBuilder()
    async for agencyplanspec in agencyplanspecs:
        ikbuilder.button(
            text=agencyplanspec.name,
            callback_data=AgentAgencyCallbackData(pk=agent.agency_id, action=AgentAgencyAction.OVERVIEW),
        )

    text = render_to_string("teleport/subscription_profile_startlink.thtml", context={"agencyplanspecs": agencyplanspecs})



@router.message(
    StartCommandQueryFilter(query_magic=query_magic_dispatcher(QueryPathName.ASSOCIATE_TO_ACCOUNT))
)
async def subscription_profile_startlink_handler(
    message: Message,
    command_query: QueryDict,
    tuser: TelegramUser | None, state: FSMContext, aiobot: Bot, bot_obj: models.TelegramBot
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()
    secret_key = command_query.get("k")
    if not secret_key:
        return
    data = await services.get_secret_key(secret_key=secret_key)
    if not data or not (subscription_profile_id := data.get("subscription_profile_id")):
        return
    subscriptionprofile_obj = await proxy_manager_models.SubscriptionProfile.objects.select_related("initial_agency", "user").aget(id=subscription_profile_id)
    transfer_ownership: bool = data.get("transfer_ownership")
    referred_by = None
    if not tuser:
        if transfer_ownership:
            user = None
        else:
            user = subscriptionprofile_obj.user
        if user is None:
            user = User()
            user.name = message.from_user.full_name
            user.username = await services.make_username(base=message.from_user.username)
            if subscriptionprofile_obj.initial_agency.defualt_timezone:
                user.preferred_timezone = subscriptionprofile_obj.initial_agency.defualt_timezone
                timezone.activate(user.preferred_timezone)
        tuser = models.TelegramUser()
        tuser.user = user
        tuser.user_tid = message.from_user.id
        tuser.tbot = bot_obj
        await user.asave()
        await tuser.asave()

    if subscriptionprofile_obj.user is None:
        subscriptionprofile_obj.user = tuser.user
        await subscriptionprofile_obj.asave()
    else:
        if subscriptionprofile_obj.user != tuser.user:
            if transfer_ownership:
                referred_by = subscriptionprofile_obj.user
                subscriptionprofile_obj.user = tuser.user
                await subscriptionprofile_obj.asave()
        else:
            # already
            pass
    await proxy_manager_models.AgencyUser.objects.aget_or_create(user=tuser.user, agency=subscriptionprofile_obj.initial_agency, defaults={"referred_by": referred_by})

    subscriptionperiod_obj = (
        await subscriptionprofile_obj.periods.filter(selected_as_current=True)
        .select_related("plan__connection_rule__inboundcombogroup")
        .ann_expires_at()
        .ann_up_bytes_remained()
        .ann_dl_bytes_remained()
        .ann_total_limit_bytes()
        .afirst()
    )

    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.button(
        text=gettext("مشاهده منو"),
        callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.MENU),
    )
    # ikbuilder.button(
    #     text=gettext("مشاهده منو"),
    #     callback_data=ContentCallbackData(pk=subscriptionprofile_obj.pk, action=SubscriptionProfileAction.GET_LINK),
    # )
    text = render_to_string("teleport/subscription_profile_startlink.thtml", context={"subscriptionperiod_obj": subscriptionperiod_obj})

    return message.answer(text, reply_markup=ikbuilder.as_markup())

