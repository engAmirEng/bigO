from typing import Optional

from asgiref.sync import sync_to_async

import aiogram.utils.deep_linking
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton, ReplyKeyboardBuilder
from bigO.proxy_manager import models as proxy_manager_models
from bigO.proxy_manager import services as proxy_manager_services
from bigO.proxy_manager.subscription.planproviders import TypeSimpleDynamic1, TypeSimpleStrict1
from bigO.telegram_bot.models import TelegramBot, TelegramUser
from bigO.telegram_bot.utils import add_message, thtml_render_to_string
from django.contrib import messages
from django.utils.translation import gettext

from ... import models
from ..base import AgentAgencyAction, AgentAgencyCallbackData
from .base import (
    AgentAgencyPlanAction,
    AgentAgencyPlanCallbackData,
    SimpleButtonCallbackData,
    SimpleButtonName,
    router,
)


@router.callback_query(AgentAgencyCallbackData.filter(aiogram.F.action == AgentAgencyAction.NEW_PROFILE))
async def agent_new_profile_handler(
    message: CallbackQuery,
    callback_data: AgentAgencyCallbackData,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()
    agency = panel_obj.agency
    try:
        agent = await proxy_manager_models.Agent.objects.aget(user=tuser.user, agency=agency)
    except proxy_manager_models.Agent.DoesNotExist:
        return message.message.answer(gettext("دسترسی این مورد را ندارید"))
    subscriptionplan_qs = proxy_manager_services.get_agent_available_plans(agency=agency)
    subscriptionplan_list = [i async for i in subscriptionplan_qs]
    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔙 " + gettext("بازکشت به منو"),
            callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.MENU).pack(),
        )
    )
    ikbuilder_plan = InlineKeyboardBuilder()
    for subscriptionplan in subscriptionplan_list:
        ikbuilder_plan.button(
            text=subscriptionplan.name,
            callback_data=AgentAgencyPlanCallbackData(
                pk=agency.id, plan_id=subscriptionplan.id, action=AgentAgencyPlanAction.NEW_PROFILE
            ),
        )
    ikbuilder_plan.adjust(2, repeat=True)
    ikbuilder.attach(ikbuilder_plan)
    text = await thtml_render_to_string(
        "teleport/agent/new_account.thtml", context={"subscriptionplan_list": subscriptionplan_list}
    )
    return message.message.edit_text(text, reply_markup=ikbuilder.as_markup())


class AgentNewSimpleDynamic1PlanForm(StatesGroup):
    plan_id = State()
    trafficGB = State()
    days = State()
    final_check = State()


class AgentNewSimpleStrict1PlanForm(StatesGroup):
    plan_id = State()
    final_check = State()


@router.callback_query(AgentAgencyPlanCallbackData.filter(aiogram.F.action == AgentAgencyPlanAction.NEW_PROFILE))
async def agent_new_profile_plan_choosed_handler(
    message: CallbackQuery,
    callback_data: AgentAgencyPlanCallbackData,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()
    choosed_plan_id = callback_data.plan_id
    agency = panel_obj.agency
    try:
        agent = await proxy_manager_models.Agent.objects.aget(user=tuser.user, agency=agency)
    except proxy_manager_models.Agent.DoesNotExist:
        return message.message.answer(gettext("دسترسی این مورد را ندارید"))
    choosed_plan_obj = (
        await proxy_manager_services.get_agent_available_plans(agency=agency).filter(id=choosed_plan_id).afirst()
    )
    if choosed_plan_obj is None:
        return message.message.answer(gettext("این پلن فعال نیست."))
    await state.update_data(plan_id=choosed_plan_id)
    if choosed_plan_obj.plan_provider_cls == TypeSimpleDynamic1:
        await state.set_state(AgentNewSimpleDynamic1PlanForm.trafficGB)
        rkbuilder = ReplyKeyboardBuilder()
        rkbuilder.button(text=gettext("انصراف"))

        return message.message.answer(gettext("حجم سرویس خود را وارد کنید:"), reply_markup=rkbuilder.as_markup())
    elif choosed_plan_obj.plan_provider_cls == TypeSimpleStrict1:
        await state.set_state(AgentNewSimpleStrict1PlanForm.final_check)
        rkbuilder = ReplyKeyboardBuilder()
        rkbuilder.button(text=gettext("تایید"))
        rkbuilder.button(text=gettext("انصراف"))
        rkbuilder.adjust(2, True)

        return message.message.answer(gettext("درحال خرید {}، تایید میکنید؟"), reply_markup=rkbuilder.as_markup())
    else:
        raise NotImplementedError


@router.message(AgentNewSimpleDynamic1PlanForm.trafficGB)
async def agent_new_profile_plan_newsimpledynamic1plan_traffic_handler(
    message: Message,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    if message.text == gettext("انصراف"):
        return
    try:
        entered_trafic_gb = int(message.text)
    except:
        rkbuilder = ReplyKeyboardBuilder()
        rkbuilder.button(text=gettext("انصراف"))

        return message.answer(
            gettext("'{0}' معتبر نیست، حجم سرویس خود را وارد کنید:").format(message.text),
            reply_markup=rkbuilder.as_markup(),
        )
    data = await state.get_data()
    choosed_plan_id = data["plan_id"]
    agency = panel_obj.agency
    try:
        agent = await proxy_manager_models.Agent.objects.select_related("user").aget(user=tuser.user, agency=agency)
    except proxy_manager_models.Agent.DoesNotExist:
        return message.answer(gettext("دسترسی این مورد را ندارید"))
    choosed_plan_obj = (
        await proxy_manager_services.get_agent_available_plans(agency=agency).filter(id=choosed_plan_id).afirst()
    )
    if choosed_plan_obj is None:
        return message.answer(gettext("این پلن فعال نیست."))
    await state.update_data(trafficGB=entered_trafic_gb)
    await state.set_state(AgentNewSimpleDynamic1PlanForm.days)
    rkbuilder = ReplyKeyboardBuilder()
    rkbuilder.button(text=gettext("انصراف"))

    return message.answer(gettext("تعداد روز سرویس خود را وارد کنید:"), reply_markup=rkbuilder.as_markup())


@router.message(AgentNewSimpleDynamic1PlanForm.days)
async def agent_new_profile_plan_newsimpledynamic1plan_days_handler(
    message: Message,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    if message.text == gettext("انصراف"):
        return
    try:
        entered_days = int(message.text)
    except:
        rkbuilder = ReplyKeyboardBuilder()
        rkbuilder.button(text=gettext("انصراف"))

        return message.answer(
            gettext("'{0}' معتبر نیست، تعداد روز سرویس خود را وارد کنید:").format(message.text),
            reply_markup=rkbuilder.as_markup(),
        )
    data = await state.get_data()
    choosed_plan_id = data["plan_id"]
    agency = panel_obj.agency
    try:
        agent = await proxy_manager_models.Agent.objects.select_related("user").aget(user=tuser.user, agency=agency)
    except proxy_manager_models.Agent.DoesNotExist:
        return message.answer(gettext("دسترسی این مورد را ندارید"))
    choosed_plan_obj = (
        await proxy_manager_services.get_agent_available_plans(agency=agency).filter(id=choosed_plan_id).afirst()
    )
    if choosed_plan_obj is None:
        return message.answer(gettext("این پلن فعال نیست."))
    await state.update_data(days=entered_days)
    await state.set_state(AgentNewSimpleDynamic1PlanForm.final_check)
    rkbuilder = ReplyKeyboardBuilder()
    rkbuilder.button(text=gettext("تایید"))
    rkbuilder.button(text=gettext("انصراف"))

    return message.answer(gettext("درحال خرید {}، تایید میکنید؟"), reply_markup=rkbuilder.as_markup())


@router.message(AgentNewSimpleDynamic1PlanForm.final_check)
@router.message(AgentNewSimpleStrict1PlanForm.final_check)
async def agent_new_profile_plan_finalcheck_handler(
    message: Message,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    from bigO.BabyUI.services import create_new_user

    if message.text == gettext("انصراف"):
        return
    data = await state.get_data()
    choosed_plan_id = data["plan_id"]
    agency = panel_obj.agency
    try:
        agent = await proxy_manager_models.Agent.objects.select_related("user").aget(user=tuser.user, agency=agency)
    except proxy_manager_models.Agent.DoesNotExist:
        return message.answer(gettext("دسترسی این مورد را ندارید"))
    choosed_plan_obj = (
        await proxy_manager_services.get_agent_available_plans(agency=agency).filter(id=choosed_plan_id).afirst()
    )
    plan_args = {}
    if choosed_plan_obj is None:
        return message.answer(gettext("این پلن فعال نیست."))
    if choosed_plan_obj.plan_provider_cls == TypeSimpleDynamic1 and isinstance(data, AgentNewSimpleDynamic1PlanForm):
        expiry_days = data.final_check
        volume_gb = data.trafficGB
        plan_args = {"total_usage_limit_bytes": volume_gb * 1000_000_000, "expiry_seconds": expiry_days * 24 * 60 * 60}
    elif choosed_plan_obj.plan_provider_cls == TypeSimpleStrict1 and isinstance(data, AgentNewSimpleStrict1PlanForm):
        pass
    else:
        raise NotImplementedError
    subscriptionperiod_obj = await sync_to_async(create_new_user)(
        agency=agency, agentuser=agent.user, plan=choosed_plan_obj, title="", plan_args=plan_args, description="fdfd"
    )
    subscriptionprofile_obj = subscriptionperiod_obj.profile
    await add_message(state=state, level=messages.SUCCESS, message=gettext("باموفقیت ایجاد شد"))
    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.button(
        text=gettext("مشاهده منو"),
        callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.MENU),
    )
    text = await thtml_render_to_string(
        "teleport/agent/subscription_profile_overview.thtml",
        context={"subscriptionprofile": subscriptionprofile_obj},
    )

    return message.answer(text, reply_markup=ikbuilder.as_markup())
