import asyncio
from enum import Enum
from typing import Optional

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
from bigO.proxy_manager import models as proxy_manager_models
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

class AgencyAction(str, Enum):
    OVERVIEW = "overview"
    NEW_PROFILE = "new_profile"

class AgencyCallbackData(CallbackData, prefix="agency"):
    pk: int
    action: AgencyAction


@router.callback_query(
    SimpleButtonCallbackData.filter(aiogram.F.button_name == SimpleButtonName.MENU)
)
@router.message(CommandStart())
async def menu_handler(
    message: CallbackQuery | Message,
    command_query: QueryDict,
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
        ikbuilder.button(
            text=gettext("خرید اکانت جدید"),
            callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.NEW_ACCOUNT_ME),
        )
    for agent in agents:
        ikbuilder.button(
            text=gettext("مدیریت {0}").format(agent.agency.name),
            callback_data=AgencyCallbackData(pk=agent.agency_id, action=AgencyAction.OVERVIEW),
        )
        ikbuilder.button(
            text=gettext("اکانت جدید {0}").format(agent.agency.name),
            callback_data=AgencyCallbackData(pk=agent.agency_id, action=AgencyAction.NEW_PROFILE),
        )

    text = render_to_string("teleport/subscription_profile_startlink.thtml", context={"subscriptionperiods": subscriptionperiods})

    return message.answer(text, reply_markup=ikbuilder.as_markup())


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
    if not tuser:
        user = subscriptionprofile_obj.user
        if user is None:
            user = User()
            user.name = message.from_user.full_name
            user.username = services.make_username(base=message.from_user.username)
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
            sentry_sdk.capture_message(f"user of {subscriptionprofile_obj} changed from {subscriptionprofile_obj.user} to {tuser.user}")
            subscriptionprofile_obj.user = tuser.user
            await subscriptionprofile_obj.asave()
        else:
            # already
            pass

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

