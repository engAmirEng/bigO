from enum import Enum
from typing import Optional

from asgiref.sync import sync_to_async

import aiogram.utils.deep_linking
from aiogram import Bot
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, CopyTextButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton, ReplyKeyboardBuilder
from bigO.BabyUI import services as BabyUI_services
from bigO.finance import models as finance_models
from bigO.finance.payment_providers.providers import BankTransfer1
from bigO.proxy_manager import models as proxy_manager_models
from bigO.proxy_manager import services as proxy_manager_services
from bigO.proxy_manager.subscription.planproviders import TypeSimpleDynamic1, TypeSimpleStrict1
from bigO.telegram_bot.models import TelegramBot, TelegramUser
from bigO.telegram_bot.utils import add_message, thtml_render_to_string
from bigO.users.models import User
from django.contrib import messages
from django.http import QueryDict
from django.utils.translation import gettext

from .. import models, services
from .base import (
    MemberAgencyAction,
    MemberAgencyCallbackData,
    ProfileAction,
    ProfileCallbackData,
    SimpleBoolCallbackData,
    SimpleButtonCallbackData,
    SimpleButtonName,
    router,
)
from .utils import QueryPathName, StartCommandQueryFilter, query_magic_dispatcher


class MemberAgencyPlanAction(str, Enum):
    NEW_PROFILE = "new_profile"


class MemberAgencyPlanCallbackData(CallbackData, prefix="member_agency"):
    agency_id: int
    plan_id: int
    action: MemberAgencyPlanAction


class MemberBillAction(str, Enum):
    OVERVIEW = "overview"
    CANCEL = "cancel"


class MemberBillCallbackData(CallbackData, prefix="member_init_paybill"):
    bill_id: int
    action: MemberBillAction


class MemberInitPaybillCallbackData(CallbackData, prefix="member_init_paybill"):
    bill_id: str | int
    payment_provider_id: str | int
    payment_id: str | int | None = None


class MemberPaybillBankTransfer1Action(str, Enum):
    CHECK_I_PAID = "check_i_paid"


class MemberPaybillBankTransfer1CallbackData(MemberInitPaybillCallbackData, prefix="member_init_paybill"):
    action: MemberPaybillBankTransfer1Action


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
    useragency = (
        await proxy_manager_models.AgencyUser.objects.filter(
            user=tuser.user, agency=agency, agency_id=callback_data.agency_id
        )
        .select_related("user", "agency")
        .afirst()
    )
    if useragency is None:
        return message.message.edit_text(gettext("تغییری ایجاد شده، ار ابتدا اقدام کنید."))

    subscriptionplan_qs = proxy_manager_services.get_user_available_plans(
        user=useragency.user, agency=useragency.agency
    )
    subscriptionplan_list = [i async for i in subscriptionplan_qs]
    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔙 " + gettext("بازکشت به منو"),
            callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.MENU).pack(),
        )
    )
    ikbuilder_plan = InlineKeyboardBuilder()
    for i, subscriptionplan in enumerate(subscriptionplan_list):
        ikbuilder_plan.button(
            text=f"{i + 1}) {subscriptionplan.name}",
            callback_data=MemberAgencyPlanCallbackData(
                agency_id=useragency.agency_id,
                plan_id=subscriptionplan.id,
                action=MemberAgencyPlanAction.NEW_PROFILE,
            ),
        )
    ikbuilder_plan.adjust(2, repeat=True)
    ikbuilder.attach(ikbuilder_plan)
    text = await thtml_render_to_string(
        "teleport/member/new_profile.thtml",
        context={"subscriptionplans": subscriptionplan_list},
    )
    return message.message.edit_text(text=text, reply_markup=ikbuilder.as_markup())


class MemberNewSimpleDynamic1PlanForm(StatesGroup):
    plan_id = State()
    trafficGB = State()
    days = State()
    bill_id = State()
    final_check = State()


class MemberNewSimpleStrict1PlanForm(StatesGroup):
    plan_id = State()
    bill_id = State()
    final_check = State()


@router.callback_query(MemberAgencyPlanCallbackData.filter(aiogram.F.action == MemberAgencyPlanAction.NEW_PROFILE))
async def member_new_profile_plan_choosed_handler(
    message: CallbackQuery,
    callback_data: MemberAgencyPlanCallbackData,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    await state.clear()
    choosed_plan_id = callback_data.plan_id
    agency = panel_obj.agency
    useragency = (
        await proxy_manager_models.AgencyUser.objects.filter(
            user=tuser.user, agency=agency, agency_id=callback_data.agency_id
        )
        .select_related("user", "agency")
        .afirst()
    )
    if useragency is None:
        return message.message.edit_text(gettext("تغییری ایجاد شده، ار ابتدا اقدام کنید."))

    choosed_plan_obj = (
        await proxy_manager_services.get_user_available_plans(user=useragency.user, agency=useragency.agency)
        .filter(id=choosed_plan_id)
        .afirst()
    )
    if choosed_plan_obj is None:
        return message.message.answer(gettext("این پلن فعال نیست."))
    await state.update_data(plan_id=choosed_plan_id)
    if choosed_plan_obj.plan_provider_cls == TypeSimpleDynamic1:
        await state.set_state(MemberNewSimpleDynamic1PlanForm.trafficGB)
        rkbuilder = ReplyKeyboardBuilder()
        rkbuilder.button(text=gettext("انصراف"))
        return message.message.answer(
            gettext("حجم(گیگابایت) سرویس خود را وارد کنید:"), reply_markup=rkbuilder.as_markup()
        )
    elif choosed_plan_obj.plan_provider_cls == TypeSimpleStrict1:
        await state.set_state(MemberNewSimpleStrict1PlanForm.final_check)
        invoice_obj = await sync_to_async(proxy_manager_services.member_create_bill)(
            plan=choosed_plan_obj, plan_args={}, agency_user=useragency, profile=None, actor=tuser.user
        )
        await state.update_data(bill_id=invoice_obj.id)
        rkbuilder = ReplyKeyboardBuilder()
        rkbuilder.button(text=gettext("تایید"))
        rkbuilder.button(text=gettext("انصراف"))
        rkbuilder.adjust(2, True)
        text = await thtml_render_to_string(
            "teleport/member/subcription_plan_bill.thtml",
            context={"invoice": invoice_obj},
        )
        return message.message.answer(text, reply_markup=rkbuilder.as_markup())
    else:
        raise NotImplementedError


@router.message(MemberNewSimpleDynamic1PlanForm.days)
@router.message(MemberNewSimpleDynamic1PlanForm.trafficGB)
@router.message(MemberNewSimpleDynamic1PlanForm.final_check)
async def agent_new_profile_plan_newsimpledynamic1plan_handler(
    message: Message,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    from .base import menu_handler

    if message.text == gettext("انصراف"):
        await add_message(state=state, level=messages.INFO, message=gettext("عملیات توسط شما کنسل شد"))
        return await menu_handler(
            message=message, tuser=tuser, state=state, aiobot=aiobot, bot_obj=bot_obj, panel_obj=panel_obj
        )
    state_data = await state.get_data()
    state_name = await state.get_state()
    choosed_plan_id = state_data["plan_id"]
    agency = panel_obj.agency
    useragency = (
        await proxy_manager_models.AgencyUser.objects.filter(user=tuser.user, agency=agency, agency_id=agency.id)
        .select_related("user", "agency")
        .afirst()
    )
    if useragency is None:
        return message.reply(gettext("تغییری ایجاد شده، ار ابتدا اقدام کنید."))
    choosed_plan_obj = (
        await proxy_manager_services.get_user_available_plans(user=useragency.user, agency=useragency.agency)
        .filter(id=choosed_plan_id)
        .afirst()
    )
    if choosed_plan_obj is None:
        return message.answer(gettext("این پلن فعال نیست."))
    if state_name == MemberNewSimpleDynamic1PlanForm.trafficGB.state:
        try:
            entered_trafic_gb = int(message.text)
        except ValueError:
            rkbuilder = ReplyKeyboardBuilder()
            rkbuilder.button(text=gettext("انصراف"))

            return message.answer(
                gettext("مقدار وارد شده معتبر نیست، لطفا حجم(گیگابایت) مدنظر سرویس خود را بصورت عدد وارد کنید:"),
                reply_markup=rkbuilder.as_markup(),
            )
        await state.update_data(trafficGB=entered_trafic_gb)
        await state.set_state(MemberNewSimpleDynamic1PlanForm.days)
        rkbuilder = ReplyKeyboardBuilder()
        rkbuilder.button(text=gettext("انصراف"))
        return message.answer(gettext("تعداد روز سرویس خود را وارد کنید:"), reply_markup=rkbuilder.as_markup())
    elif state_name == MemberNewSimpleDynamic1PlanForm.days.state:
        try:
            entered_days = int(message.text)
        except ValueError:
            rkbuilder = ReplyKeyboardBuilder()
            rkbuilder.button(text=gettext("انصراف"))

            return message.answer(
                gettext("مقدار وارد شده معتبر نیست، لطفا تعداد روز سرویس مدنظر خود را بصورت عدد وارد کنید:"),
                reply_markup=rkbuilder.as_markup(),
            )
        volume_gb = state_data["trafficGB"]
        plan_args = {
            "total_usage_limit_bytes": volume_gb * 1000_000_000,
            "expiry_seconds": entered_days * 24 * 60 * 60,
        }
        invoice_obj = await sync_to_async(proxy_manager_services.member_create_bill)(
            plan=choosed_plan_obj, plan_args=plan_args, agency_user=useragency, profile=None, actor=tuser.user
        )
        await state.update_data(days=entered_days)
        await state.set_state(MemberNewSimpleDynamic1PlanForm.final_check)
        await state.update_data(bill_id=invoice_obj.id)
        rkbuilder = ReplyKeyboardBuilder()
        rkbuilder.button(text=gettext("تایید"))
        rkbuilder.button(text=gettext("انصراف"))
        rkbuilder.adjust(2, True)
        text = await thtml_render_to_string(
            "teleport/member/subcription_plan_bill.thtml",
            context={"invoice": invoice_obj},
        )
        return message.answer(text, reply_markup=rkbuilder.as_markup())
    elif state_name == MemberNewSimpleDynamic1PlanForm.final_check.state:
        bill_id = state_data["bill_id"]
        return await tmp_return_bill(
            message=message, bill_id=bill_id, useragency=useragency, user=tuser.user, state=state
        )

    raise NotImplementedError


@router.message(MemberNewSimpleStrict1PlanForm.final_check)
async def agent_new_profile_plan_simplestrict1_handler(
    message: Message,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    from .base import menu_handler

    if message.text == gettext("انصراف"):
        return await menu_handler(
            message=message, tuser=tuser, state=state, aiobot=aiobot, bot_obj=bot_obj, panel_obj=panel_obj
        )
    state_data = await state.get_data()
    state_name = await state.get_state()
    choosed_plan_id = state_data["plan_id"]
    agency = panel_obj.agency
    useragency = (
        await proxy_manager_models.AgencyUser.objects.filter(user=tuser.user, agency=agency, agency_id=agency.id)
        .select_related("user", "agency")
        .afirst()
    )
    if useragency is None:
        return message.answer(gettext("تغییری ایجاد شده، ار ابتدا اقدام کنید."))
    choosed_plan_obj = (
        await proxy_manager_services.get_user_available_plans(user=useragency.user, agency=useragency.agency)
        .filter(id=choosed_plan_id)
        .afirst()
    )
    if choosed_plan_obj is None:
        return message.answer(gettext("این پلن فعال نیست."))
    if state_name == MemberNewSimpleStrict1PlanForm.final_check.state:
        state_data = await state.get_data()
        bill_id = state_data["bill_id"]
        return await tmp_return_bill(
            message=message, bill_id=bill_id, useragency=useragency, user=tuser.user, state=state
        )
    raise NotImplementedError


async def tmp_return_bill(*, message, bill_id, useragency, user, state):
    agency = useragency.agency
    subscriptionplaninvoiceitem_obj = (
        await proxy_manager_models.SubscriptionPlanInvoiceItem.objects.select_related("invoice")
        .filter(invoice_id=bill_id, issued_to=useragency)
        .afirst()
    )
    if (
        subscriptionplaninvoiceitem_obj is None
        or subscriptionplaninvoiceitem_obj.invoice.status != finance_models.Invoice.StatusChoices.DRAFT
    ):
        return
    invoice = subscriptionplaninvoiceitem_obj.invoice
    if message.text != gettext("تایید"):
        rkbuilder = ReplyKeyboardBuilder()
        rkbuilder.button(text=gettext("تایید"))
        rkbuilder.button(text=gettext("انصراف"))
        text = await thtml_render_to_string(
            "teleport/member/subcription_plan_bill.thtml",
            context={"invoice": subscriptionplaninvoiceitem_obj.invoice},
        )
        return message.answer(text=text, reply_markup=rkbuilder.as_markup())
    paymentproviders_qs = proxy_manager_services.get_user_available_paymentproviders(user=user, agency=agency)
    paymentproviders_list: list[finance_models.PaymentProvider] = [i async for i in paymentproviders_qs]
    if not paymentproviders_list:
        return message.answer(gettext("درگاه فعالی وجود ندارد، با ادمین تماس بگیرید"))
    changed = await sync_to_async(proxy_manager_services.member_prepare_checkout)(invoice)
    await state.clear()
    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.row(
        InlineKeyboardButton(
            text="❌ " + gettext("انصراف"),
            callback_data=MemberBillCallbackData(bill_id=invoice.id, action=MemberBillAction.CANCEL).pack(),
        ),
        InlineKeyboardButton(
            text="🔄 " + gettext("بروزرسانی وضعیت"),
            callback_data=MemberBillCallbackData(bill_id=invoice.id, action=MemberBillAction.OVERVIEW).pack(),
        ),
    )
    for paymentprovider in paymentproviders_list:
        ikbuilder.row(
            InlineKeyboardButton(
                text=gettext("پرداخت با ") + paymentprovider.name,
                callback_data=MemberInitPaybillCallbackData(
                    bill_id=invoice.id, payment_provider_id=paymentprovider.id
                ).pack(),
            )
        )
    text = await thtml_render_to_string(
        "teleport/member/subcription_plan_checkout.thtml",
        context={"invoice": invoice},
    )
    return message.answer(text, reply_markup=ikbuilder.as_markup())


@router.callback_query(MemberBillCallbackData.filter(aiogram.F.action == MemberBillAction.OVERVIEW))
async def new_billoverview_handler(
    message: CallbackQuery,
    callback_data: MemberBillCallbackData,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    agency = panel_obj.agency
    useragency = (
        await proxy_manager_models.AgencyUser.objects.filter(
            user=tuser.user,
            agency=agency,
        )
        .select_related("user", "agency")
        .afirst()
    )
    if useragency is None:
        return message.message.edit_text(gettext("تغییری ایجاد شده، ار ابتدا اقدام کنید."))

    subscriptionplaninvoiceitem_obj = (
        await proxy_manager_models.SubscriptionPlanInvoiceItem.objects.select_related("invoice")
        .filter(invoice_id=callback_data.bill_id, issued_to=useragency)
        .afirst()
    )
    invoice = subscriptionplaninvoiceitem_obj.invoice
    if subscriptionplaninvoiceitem_obj is None:
        return
    if invoice.status == finance_models.Invoice.StatusChoices.ISSUED:
        paymentproviders_qs = proxy_manager_services.get_user_available_paymentproviders(
            user=tuser.user, agency=agency
        )
        paymentproviders_list: list[finance_models.PaymentProvider] = [i async for i in paymentproviders_qs]
        if not paymentproviders_list:
            return message.answer(gettext("درگاه فعالی وجود ندارد، با ادمین تماس بگیرید"))
        changed = await sync_to_async(proxy_manager_services.member_prepare_checkout)(invoice)
        if changed:
            await add_message(state=state, level=messages.INFO, message=gettext("تغییر یافت شدس"))
        await state.clear()
        ikbuilder = InlineKeyboardBuilder()
        ikbuilder.row(
            InlineKeyboardButton(
                text="❌ " + gettext("انصراف"),
                callback_data=MemberBillCallbackData(bill_id=invoice.id, action=MemberBillAction.CANCEL).pack(),
            ),
            InlineKeyboardButton(
                text="🔄 " + gettext("بروزرسانی وضعیت"),
                callback_data=MemberBillCallbackData(bill_id=invoice.id, action=MemberBillAction.OVERVIEW).pack(),
            ),
        )
        for paymentprovider in paymentproviders_list:
            ikbuilder.row(
                InlineKeyboardButton(
                    text=gettext("پرداخت با ") + paymentprovider.name,
                    callback_data=MemberInitPaybillCallbackData(
                        bill_id=invoice.id, payment_provider_id=paymentprovider.id
                    ).pack(),
                )
            )
        text = await thtml_render_to_string(
            "teleport/member/subcription_plan_checkout.thtml",
            context={"invoice": invoice},
        )
        return message.message.edit_text(text, reply_markup=ikbuilder.as_markup())
    raise NotImplementedError


@router.callback_query(MemberInitPaybillCallbackData.filter())
@router.callback_query(
    MemberPaybillBankTransfer1CallbackData.filter(aiogram.F.action == MemberPaybillBankTransfer1Action.CHECK_I_PAID)
)
async def member_initpaybill_handler(
    message: CallbackQuery,
    callback_data: MemberInitPaybillCallbackData | MemberPaybillBankTransfer1CallbackData,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    agency = panel_obj.agency
    useragency = (
        await proxy_manager_models.AgencyUser.objects.filter(
            user=tuser.user,
            agency=agency,
        )
        .select_related("user", "agency")
        .afirst()
    )
    if useragency is None:
        return message.message.edit_text(gettext("تغییری ایجاد شده، ار ابتدا اقدام کنید."))
    bill_id = callback_data.bill_id
    payment_provider_id = callback_data.payment_provider_id
    payment_id = callback_data.payment_id
    subscriptionplaninvoiceitem_obj = (
        await proxy_manager_models.SubscriptionPlanInvoiceItem.objects.select_related("invoice")
        .filter(invoice_id=bill_id, issued_to=useragency)
        .afirst()
    )
    invoice = subscriptionplaninvoiceitem_obj.invoice
    if subscriptionplaninvoiceitem_obj is None:
        return
    if invoice.status != finance_models.Invoice.StatusChoices.ISSUED:
        return message.answer(
            gettext(("امکان پذیر نیست، این صورت حساب در وضعیت {0} قرار دارد")).format(invoice.get_status_diplay())
        )
    paymentproviders_qs = proxy_manager_services.get_user_available_paymentproviders(user=tuser.user, agency=agency)
    paymentprovider_obj: finance_models.PaymentProvider | None = await paymentproviders_qs.filter(
        id=payment_provider_id
    ).afirst()
    if paymentprovider_obj is None:
        return message.answer(gettext("درگاه فعالی وجود ندارد، با ادمین تماس بگیرید"))
    provider_cls = paymentprovider_obj.provider_cls
    if isinstance(callback_data, MemberPaybillBankTransfer1CallbackData) and provider_cls != BankTransfer1:
        return message.answer(gettext("عدم تطابق"))
    other_paymentproviders_list: list[finance_models.PaymentProvider] = [
        i async for i in paymentproviders_qs if str(i.id) != str(payment_provider_id)
    ]
    changed = await sync_to_async(proxy_manager_services.member_prepare_checkout)(invoice)
    if changed:
        await add_message(state=state, level=messages.INFO, message=gettext("تغییر قیمت اعمال شد."))

    provider_args = paymentprovider_obj.get_provider_args()
    if payment_id:
        payment = await finance_models.Payment.objects.filter(id=payment_id, user=tuser.user, invoice=invoice).afirst()
        if payment is None:
            return message.answer(gettext("یافت نشد، با ادمین تماس بگیرید"))
    else:
        payment = await sync_to_async(finance_models.Payment.init_payment)(
            invoice=invoice, provider=paymentprovider_obj, user=tuser.user
        )
    ikbuilder = InlineKeyboardBuilder()
    if provider_cls == BankTransfer1:
        if isinstance(callback_data, MemberPaybillBankTransfer1CallbackData):
            if callback_data.action == MemberPaybillBankTransfer1Action.CHECK_I_PAID:
                res = gettext(
                    "درصورتی که مبلغ {0} واریز شده باشد توسط سیستم برسی میشود و به شما اطلاع داده خواهد شد"
                ).format(str(payment.amount))
                return message.answer(res)
        ikbuilder.row(
            InlineKeyboardButton(
                text="👍 " + gettext("واریز شد"),
                callback_data=MemberPaybillBankTransfer1CallbackData(
                    bill_id=invoice.id,
                    payment_provider_id=payment_provider_id,
                    payment_id=payment.id,
                    action=MemberPaybillBankTransfer1Action.CHECK_I_PAID,
                ).pack(),
            ),
        )
        text = await thtml_render_to_string(
            "teleport/member/subcription_plan_banktransfer1.thtml",
            context={"invoice": invoice, "payment": payment, "provider_args": provider_args},
        )
    else:
        raise NotImplementedError
    ikbuilder.row(
        InlineKeyboardButton(
            text="❌ " + gettext("لغو و بازگشت"),
            callback_data=MemberBillCallbackData(bill_id=invoice.id, action=MemberBillAction.OVERVIEW).pack(),
        ),
        InlineKeyboardButton(
            text="🔄 " + gettext("بروزرسانی وضعیت"),
            callback_data=MemberInitPaybillCallbackData(
                bill_id=invoice.id, payment_id=payment.id, payment_provider_id=payment_provider_id
            ).pack(),
        ),
    )
    if other_paymentproviders_list:
        ikbuilder.row(
            InlineKeyboardButton(
                text=gettext("پرداخت با سایر متد های پرداخت") + " 👇",
                callback_data="dummy",
            )
        )
    for paymentprovider in other_paymentproviders_list:
        ikbuilder.row(
            InlineKeyboardButton(
                text=gettext("پرداخت با ") + paymentprovider.name,
                callback_data=MemberInitPaybillCallbackData(
                    bill_id=invoice.id, payment_provider_id=paymentprovider.id
                ).pack(),
            )
        )
    return message.message.edit_text(text, reply_markup=ikbuilder.as_markup())


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
        subscriptionprofile_obj.user = user
        await subscriptionprofile_obj.asave()
        msg = gettext("مالکیت اکانت {0} به شما({1}) منتقل شد.").format(str(subscriptionprofile_obj), str(user))
    else:
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
                msg = gettext("مالکیت اکانت {0} از قبل به دیگری اختصاص یافته.").format(str(subscriptionprofile_obj))
        else:
            msg = gettext("از قبل به اکانت خود متصل بودید.")
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
    text = await thtml_render_to_string(
        "teleport/member/subscription_profile_startlink.thtml",
        context={"msg": msg, "subscriptionprofile": subscriptionprofile_obj},
    )

    return message.answer(text, reply_markup=ikbuilder.as_markup())


@router.callback_query(SimpleButtonCallbackData.filter(aiogram.F.button_name == SimpleButtonName.ACCOUNTS_ME))
async def my_account_detail_handler(
    message: CallbackQuery,
    callback_data: SimpleButtonCallbackData,
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
    return message.answer(gettext("یکی از اکانت های خود را انتخاب کنید"))


@router.callback_query(ProfileCallbackData.filter(aiogram.F.action == ProfileAction.DETAIL))
async def my_account_detail_handler(
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
            text="💳 " + gettext("شارژ این اکانت"),
            callback_data=ProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=ProfileAction.RENEW
            ).pack(),
        ),
    )
    normal_sublink = await sync_to_async(subscriptionprofile_obj.get_sublink)()
    ikbuilder.row(
        InlineKeyboardButton(
            text="⚿ " + gettext("کپی لینک اشتراک اندروید"),
            copy_text=CopyTextButton(text=normal_sublink),
        ),
        InlineKeyboardButton(
            text="⚿ " + gettext("کپی لینک اشتراک ios"),
            copy_text=CopyTextButton(text=normal_sublink + "?base64=true"),
        ),
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔐 " + gettext("عوض کردن رمز اتصال"),
            callback_data=ProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=ProfileAction.PASS_CHANGE
            ).pack(),
        ),
        InlineKeyboardButton(
            text="🎁 " + gettext("هدیه به دوست"),
            callback_data=ProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=ProfileAction.TRANSFER_TO_ANOTHER
            ).pack(),
        ),
    )

    text = await thtml_render_to_string(
        "teleport/member/subscription_profile_startlink.thtml",
        context={"msg": "", "subscriptionprofile": subscriptionprofile_obj},
    )
    return message.message.edit_text(text, reply_markup=ikbuilder.as_markup())


@router.callback_query(ProfileCallbackData.filter(aiogram.F.action == ProfileAction.TRANSFER_TO_ANOTHER))
async def my_account_transfer_to_another_handler(
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
        subscriptionprofile_obj = await proxy_manager_models.SubscriptionProfile.objects.filter(
            user=user, initial_agency=agency
        ).aget(id=callback_data.profile_id)
    except proxy_manager_models.SubscriptionProfile.DoesNotExist:
        return message.answer(gettext("اکانت یافت نشد."))

    startlink = services.get_subscription_profile_startlink(
        bot_obj=bot_obj, subscription_profile=subscriptionprofile_obj, transfer_ownership=True
    )
    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔙 " + gettext("بازگشت"),
            callback_data=ProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=ProfileAction.DETAIL
            ).pack(),
        )
    )
    text = await thtml_render_to_string(
        "teleport/member/subscription_profile_transfer_to_another.thtml",
        context={"startlink": startlink, "subscriptionprofile": subscriptionprofile_obj},
    )
    return message.message.edit_text(text, reply_markup=ikbuilder.as_markup())


@router.callback_query(ProfileCallbackData.filter(aiogram.F.action == ProfileAction.PASS_CHANGE))
async def my_account_passchange_request_handler(
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
        subscriptionprofile_obj = await proxy_manager_models.SubscriptionProfile.objects.filter(
            user=user, initial_agency=agency
        ).aget(id=callback_data.profile_id)
    except proxy_manager_models.SubscriptionProfile.DoesNotExist:
        return message.answer(gettext("اکانت یافت نشد."))

    await state.set_state(PassChangeForm.requested)

    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔙 " + gettext("انصراف"),
            callback_data=ProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=ProfileAction.DETAIL
            ).pack(),
        ),
        InlineKeyboardButton(
            text="🔄 تایید",
            callback_data=SimpleBoolCallbackData(result=True).pack(),
        ),
    )

    text = await thtml_render_to_string(
        "teleport/member/subscription_profile_passchange_request.thtml",
        context={"msg": "", "subscriptionprofile": subscriptionprofile_obj},
    )
    return message.message.edit_text(text, reply_markup=ikbuilder.as_markup())


class PassChangeForm(StatesGroup):
    requested = State()
    approved = State()


@router.callback_query(SimpleBoolCallbackData.filter(aiogram.F.result == True), PassChangeForm.requested)
async def my_account_passchange_done_handler(
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
        subscriptionprofile_obj: proxy_manager_models.SubscriptionProfile = await (
            proxy_manager_models.SubscriptionProfile.objects.filter(user=user, initial_agency=agency)
        ).aget(
            id=callback_data.profile_id
        )
    except proxy_manager_models.SubscriptionProfile.DoesNotExist:
        return message.answer(gettext("اکانت یافت نشد."))

    await sync_to_async(BabyUI_services.pass_change_profile)(profile=subscriptionprofile_obj, user=user)
    await state.set_state(PassChangeForm.approved)

    ikbuilder = InlineKeyboardBuilder()
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔙 " + gettext("بازکشت"),
            callback_data=ProfileCallbackData(
                profile_id=subscriptionprofile_obj.id, action=ProfileAction.DETAIL
            ).pack(),
        )
    )
    normal_sublink = await sync_to_async(subscriptionprofile_obj.get_sublink)()
    InlineKeyboardButton(
        text="⚿ " + gettext("کپی لینک اشتراک جدید(اندروید)"),
        copy_text=CopyTextButton(text=normal_sublink),
    ),
    InlineKeyboardButton(
        text="⚿ " + gettext("کپی لینک اشتراک جدید(ios)"),
        copy_text=CopyTextButton(text=normal_sublink + "?base64=true"),
    ),

    text = await thtml_render_to_string(
        "teleport/member/subscription_profile_passchange_done.thtml",
        context={"msg": "", "subscriptionprofile": subscriptionprofile_obj},
    )
    return message.message.edit_text(text, reply_markup=ikbuilder.as_markup())
