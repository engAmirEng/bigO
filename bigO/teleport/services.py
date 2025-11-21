import json
import random
import string
from enum import Enum

from asgiref.sync import sync_to_async

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bigO.finance import models as finance_models
from bigO.proxy_manager import models as proxy_manager_models
from bigO.proxy_manager import services as proxy_manager_services
from bigO.telegram_bot import models as telegram_bot_models
from bigO.users.models import User
from django.core.cache import cache
from django.db.models import Exists, OuterRef, Q
from django.utils.translation import gettext

from ..telegram_bot.utils import thtml_render_to_string
from . import models


class TelegramBotNotSet(Exception):
    pass


def get_user_startlink(bot_obj: telegram_bot_models.TelegramBot, user: User, transfer_ownership: bool = False) -> str:
    from .dispatchers import QueryPathName, get_dispatch_query

    key = set_secret_key(data={"user_id": user.id, "transfer_ownership": transfer_ownership}, length=10)
    link = get_dispatch_query(bot_username=bot_obj.tusername, pathname=QueryPathName.ASSOCIATE_TO_USER, k=key)
    return link


def get_subscription_profile_startlink(
    bot_obj: telegram_bot_models.TelegramBot,
    subscription_profile: proxy_manager_models.SubscriptionProfile,
    transfer_ownership: bool = False,
) -> str:
    from .dispatchers import QueryPathName, get_dispatch_query

    key = set_secret_key(
        data={"subscription_profile_id": subscription_profile.id, "transfer_ownership": transfer_ownership}, length=10
    )
    link = get_dispatch_query(bot_username=bot_obj.tusername, pathname=QueryPathName.ASSOCIATE_TO_ACCOUNT, k=key)
    return link


def set_secret_key(data: dict, length: int) -> str:
    allowed_characters = string.ascii_letters + string.digits + "-" + "_"
    secret_key = "".join(random.choice(allowed_characters) for _ in range(length))
    json_data = json.dumps(data)
    cache.set(secret_key, json_data, timeout=24 * 60 * 60)
    return secret_key


async def get_secret_key(secret_key: str) -> dict | None:
    json_data = await cache.aget(secret_key)
    if json_data is None:
        return
    data = json.loads(json_data)
    return data


async def make_username(base=None, length=15) -> str:
    if base:
        base = f"{base}-"
    else:
        base = ""
    length -= len(base)
    characters = string.ascii_letters + string.digits
    while True:
        username = base + "".join(random.choice(characters) for _ in range(length))
        if not await User.objects.filter(username=username).aexists():
            return username


class AdminBankTransfer1Action(str, Enum):
    YES_PAID = "yes_paid"
    NOT_YET_PAID = "not_yet_paid"
    CANCEL_PAID = "cancel_paid"
    OVERVIEW = "overview"


class AdminBankTransfer1CallbackData(CallbackData, prefix="adminbanktransfer1"):
    payment_id: str | int
    action: AdminBankTransfer1Action


async def bank_transfer1_pend(sender, admin: User, payment: finance_models.Payment, **kwargs):
    invoice = await sync_to_async(lambda: payment.invoice)()
    related_agency = await proxy_manager_services.get_invoice_agency(invoice=invoice)
    if related_agency is None:
        return
    payment_provider = await sync_to_async(lambda: payment.provider)()
    provider_args = payment_provider.provider_args
    agency_user_qs = proxy_manager_models.AgencyUser.objects.filter(agency=related_agency, user=OuterRef("user"))
    payment_tuser = (
        await telegram_bot_models.TelegramUser.objects.filter(Q(user_id=payment.user_id) & Exists(agency_user_qs))
        .select_related("bot")
        .order_by("-last_accessed_at")
        .afirst()
    )
    panel_qs = models.Panel.objects.filter(is_active=True, agency=related_agency, bot=OuterRef("bot"))
    admin_tusers_qs = (
        telegram_bot_models.TelegramUser.objects.filter(
            Q(user=admin, bot__is_revoked=False, bot__is_powered_off=False) & Exists(panel_qs)
        )
        .select_related("bot")
        .order_by("-last_accessed_at")
    )
    admin_tusers_list = [i async for i in admin_tusers_qs]
    if not admin_tusers_list:
        return

    ikbuilder = InlineKeyboardBuilder()

    ikbuilder.row(
        InlineKeyboardButton(
            text="✅ " + gettext("بلی شده"),
            callback_data=AdminBankTransfer1CallbackData(
                payment_id=payment.id, action=AdminBankTransfer1Action.YES_PAID
            ).pack(),
        ),
        InlineKeyboardButton(
            text="❓ " + gettext("هنوز نشده"),
            callback_data=AdminBankTransfer1CallbackData(
                payment_id=payment.id, action=AdminBankTransfer1Action.NOT_YET_PAID
            ).pack(),
        ),
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔄 " + gettext("بروزرسانی وضعیت"),
            callback_data=AdminBankTransfer1CallbackData(
                payment_id=payment.id, action=AdminBankTransfer1Action.OVERVIEW
            ).pack(),
        )
    )

    for tuser in admin_tusers_list:
        tuser: telegram_bot_models.TelegramUser
        aiobot = tuser.bot.get_aiobot()

        text = await thtml_render_to_string(
            "teleport/admin/subcription_plan_banktransfer1.thtml",
            context={
                "state": None,
                "bot_obj": tuser.bot,
                "invoice": invoice,
                "payment": payment,
                "provider_args": provider_args,
                "payment_tuser": payment_tuser,
            },
        )

        await aiobot.send_message(chat_id=tuser.tid, text=text, reply_markup=ikbuilder.as_markup())
