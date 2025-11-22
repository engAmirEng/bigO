import json
import random
import string
from enum import Enum

from asgiref.sync import async_to_sync, sync_to_async

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from bigO.finance import models as finance_models
from bigO.proxy_manager import models as proxy_manager_models
from bigO.proxy_manager import services as proxy_manager_services
from bigO.telegram_bot import models as telegram_bot_models
from bigO.users.models import User
from django.core.cache import cache
from django.db import transaction
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


@transaction.atomic(using="main")
def handle_profile_startlink(
    transfer_ownership: bool, user, tuser, subscriptionprofile_obj, bot_obj, agency, from_user_t
):
    referred_by = None
    referlink_obj = None
    if not user:
        if transfer_ownership:
            user = None
        else:
            user = subscriptionprofile_obj.user
        if user is None:
            user = User()
            user.name = from_user_t.full_name
            user.username = async_to_sync(make_username)(base=from_user_t.username)
        user.save()
        if tuser is None:
            tuser = telegram_bot_models.TelegramUser()
            tuser.user = user
            tuser.tid = from_user_t.id
            tuser.bot = bot_obj
        else:
            tuser.user = user
        tuser.save()

    if subscriptionprofile_obj.user is None:
        subscriptionprofile_obj.user = user
        subscriptionprofile_obj.save()
        msg = gettext("مالکیت اکانت {0} به شما({1}) منتقل شد.").format(str(subscriptionprofile_obj), str(user))
    else:
        if subscriptionprofile_obj.user != user:
            if transfer_ownership:
                try:
                    referred_by = proxy_manager_models.AgencyUser.objects.get(
                        user=subscriptionprofile_obj.user, agency=agency
                    )
                except proxy_manager_models.AgencyUser.DoesNotExist:
                    pass
                else:
                    referlink_obj = (
                        proxy_manager_models.ReferLink.objects.filter(agency_user=referred_by, is_active=True)
                        .ann_remainded_cap_count()
                        .filter(remainded_cap_count__gt=0)
                        .first()
                    )
                subscriptionprofile_obj.user = user
                subscriptionprofile_obj.save()
                msg = gettext("مالکیت اکانت {0} از {1} به شما({2}) منتقل شد.").format(
                    str(subscriptionprofile_obj), str(referred_by), str(user)
                )
            else:
                msg = gettext("مالکیت اکانت {0} از قبل به دیگری اختصاص یافته.").format(str(subscriptionprofile_obj))
        else:
            msg = gettext("از قبل به اکانت خود متصل بودید.")
    agencyuser, created = proxy_manager_models.AgencyUser.objects.get_or_create(
        user=tuser.user, agency=subscriptionprofile_obj.initial_agency
    )
    if created:
        referlink = proxy_manager_models.ReferLink()
        referlink.agency_user = agencyuser
        referlink.capacity = 4
        characters = string.ascii_letters + string.digits
        referlink.secret = "".join(random.choice(characters) for _ in range(10))
        referlink.save()
    if created and referred_by:
        if not referlink_obj:
            transaction.set_rollback(True)
            msg = gettext("غیر قابل انجام، ظرفیت معرفی کاربر {0} به اتمام رسیده است").format(referred_by.user)
            return False, msg
        else:
            agencyuser.link_referred_by = referlink_obj
            agencyuser.save()

            groups_qs = proxy_manager_models.AgencyUserGroup.objects.filter(users=referred_by.user, agency=referred_by.agency)
            for group in groups_qs:
                group.users.add(agencyuser.user)

    return True, msg


def get_referlinklink(bot_obj: telegram_bot_models.TelegramBot, referlink: proxy_manager_models.ReferLink):
    from .dispatchers import QueryPathName, get_dispatch_query

    return get_dispatch_query(
        bot_username=bot_obj.tusername, pathname=QueryPathName.MEMBER_REFERLINK, secret=referlink.secret
    )


@transaction.atomic(using="main")
def agencyuser_from_referlink(from_user_t, user, tuser, agency, referlink, bot_obj):
    if user is None:
        user = User()
        user.name = from_user_t.full_name
        user.username = async_to_sync(make_username)(base=from_user_t.username)
        user.save()
    if tuser is None:
        tuser = telegram_bot_models.TelegramUser()
        tuser.user = user
        tuser.tid = from_user_t.id
        tuser.bot = bot_obj
    else:
        tuser.user = user
    tuser.save()
    agencyuser = proxy_manager_models.AgencyUser()
    agencyuser.user = user
    agencyuser.agency = agency
    agencyuser.link_referred_by = referlink
    agencyuser.save()

    new_referlink = proxy_manager_models.ReferLink()
    new_referlink.agency_user = agencyuser
    new_referlink.capacity = 4
    characters = string.ascii_letters + string.digits
    new_referlink.secret = "".join(random.choice(characters) for _ in range(10))
    new_referlink.save()

    groups_qs = proxy_manager_models.AgencyUserGroup.objects.filter(users=referlink.agency_user.user, agency=agency)
    for group in groups_qs:
        group.users.add(agencyuser.user)

    return agencyuser
