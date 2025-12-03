from typing import Optional

from asgiref.sync import sync_to_async

import aiogram.utils.deep_linking
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from bigO.finance import models as finance_models
from bigO.telegram_bot.models import TelegramBot, TelegramUser
from bigO.telegram_bot.utils import add_message, thtml_render_to_string
from bigO.users.models import User
from django.contrib import messages
from django.utils.translation import gettext

from .. import models, services
from ..types import (
    MemberBillAction,
    MemberBillCallbackData,
)
from .base import router


@router.callback_query(services.AdminBankTransfer1CallbackData.filter())
async def member_initpaybill_handler(
    message: CallbackQuery,
    callback_data: services.AdminBankTransfer1CallbackData,
    tuser: TelegramUser | None,
    state: FSMContext,
    aiobot: Bot,
    bot_obj: TelegramBot,
    panel_obj: models.Panel,
) -> Optional[aiogram.methods.TelegramMethod]:
    user = tuser.user
    if user is None:
        return
    payment: finance_models.Payment = (
        await finance_models.Payment.objects.filter(id=callback_data.payment_id)
        .select_related("provider", "invoice")
        .afirst()
    )
    if payment is None:
        return message.answer(gettext("نامعتبر"))
    try:
        await payment.provider.admins.aget(id=tuser.user.id)
    except User.DoesNotExist:
        return message.answer(gettext("دسترسی ندارید"))
    invoice = payment.invoice
    provider_args = payment.provider.provider_args
    payment_tuser = await TelegramUser.objects.filter(user_id=payment.user_id).select_related("bot").afirst()
    payment_tuser_aiobot = payment_tuser.bot.get_aiobot()

    if callback_data.action == services.AdminBankTransfer1Action.YES_PAID:
        if payment.status == finance_models.Payment.PaymentStatusChoices.PENDING:
            await sync_to_async(payment.complete)(actor=tuser.user)
            await add_message(state=state, level=messages.SUCCESS, message=gettext("انجام شد"))

            text = gettext("صورت حساب {0} تایید شد").format(payment.invoice.uuid.hex[:8])
            ikbuilder = InlineKeyboardBuilder()
            ikbuilder.row(
                InlineKeyboardButton(
                    text="🛍 " + gettext("مشاهده جزییات"),
                    callback_data=MemberBillCallbackData(
                        bill_id=payment.invoice_id, action=MemberBillAction.OVERVIEW
                    ).pack(),
                )
            )
            await payment_tuser_aiobot.send_message(
                chat_id=payment_tuser.tid, text=text, reply_markup=ikbuilder.as_markup()
            )
        else:
            await add_message(state=state, level=messages.ERROR, message="امکان تایید وجود ندارد")
    elif callback_data.action == services.AdminBankTransfer1Action.NOT_YET_PAID:
        if payment.status == finance_models.Payment.PaymentStatusChoices.PENDING:
            await add_message(state=state, level=messages.INFO, message=gettext("اطلاع داده شد"))
            text = gettext("کارت به کارت مربوط به صورت حساب {0} هنوز به حساب ننشسته است.").format(
                payment.invoice.uuid.hex[:8]
            )
            await payment_tuser_aiobot.send_message(chat_id=payment_tuser.tid, text=text)
        else:
            await add_message(state=state, level=messages.ERROR, message="قبلا تایید شده است")
    elif callback_data.action == services.AdminBankTransfer1Action.CANCEL_PAID:
        raise NotImplementedError

    ikbuilder = InlineKeyboardBuilder()
    if payment.status == finance_models.Payment.PaymentStatusChoices.COMPLETED:
        ikbuilder.row(
            InlineKeyboardButton(
                text="‼️ " + gettext("لغو تایید"),
                callback_data=services.AdminBankTransfer1CallbackData(
                    payment_id=payment.id, action=services.AdminBankTransfer1Action.CANCEL_PAID
                ).pack(),
            )
        )
    elif payment.status == finance_models.Payment.PaymentStatusChoices.PENDING:
        ikbuilder.row(
            InlineKeyboardButton(
                text="✅ " + gettext("بلی شده"),
                callback_data=services.AdminBankTransfer1CallbackData(
                    payment_id=payment.id, action=services.AdminBankTransfer1Action.YES_PAID
                ).pack(),
            ),
            InlineKeyboardButton(
                text="❓ " + gettext("هنوز نشده"),
                callback_data=services.AdminBankTransfer1CallbackData(
                    payment_id=payment.id, action=services.AdminBankTransfer1Action.NOT_YET_PAID
                ).pack(),
            ),
        )
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔄 " + gettext("بروزرسانی وضعیت"),
            callback_data=services.AdminBankTransfer1CallbackData(
                payment_id=payment.id, action=services.AdminBankTransfer1Action.OVERVIEW
            ).pack(),
        )
    )
    text = await thtml_render_to_string(
        "teleport/admin/subcription_plan_banktransfer1.thtml",
        context={
            "state": state,
            "bot_obj": bot_obj,
            "invoice": invoice,
            "payment": payment,
            "provider_args": provider_args,
            "payment_tuser": payment_tuser,
        },
    )
    return message.message.edit_text(text=text, reply_markup=ikbuilder.as_markup())
