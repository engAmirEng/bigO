from aiogram.types import CopyTextButton, InlineKeyboardButton
from django.utils.translation import gettext

from .types import *


def ik_member_overview_layout(ikbuilder, subscriptionprofile_id: int, agency_id: int, normal_sublink: str):
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔙 " + gettext("بازکشت به منو"),
            callback_data=SimpleButtonCallbackData(button_name=SimpleButtonName.MENU).pack(),
        ),
        InlineKeyboardButton(
            text="🔄 Refresh",
            callback_data=MemberAgencyProfileCallbackData(
                profile_id=subscriptionprofile_id, action=MemberAgencyProfileAction.DETAIL
            ).pack(),
        ),
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔋 " + gettext("تمدید این اکانت"),
            callback_data=MemberAgencyProfileCallbackData(
                profile_id=subscriptionprofile_id, action=MemberAgencyProfileAction.LIST_AVAILABLE_PLANS
            ).pack(),
        ),
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text="📚 " + gettext("نحوه اتصال"),
            callback_data=MemberAgencyCallbackData(
                agency_id=agency_id, action=MemberAgencyAction.SEE_TOTURIAL_CONTENT
            ).pack(),
        ),
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text="⚿ " + gettext("لینک اشتراک اندروید"),
            copy_text=CopyTextButton(text=normal_sublink),
        ),
        InlineKeyboardButton(
            text="⚿ " + gettext("لینک اشتراک ios"),
            copy_text=CopyTextButton(text=normal_sublink + "?base64=true"),
        ),
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text="📑 " + gettext("پروکسی ها"),
            callback_data=MemberAgencyProfileCallbackData(
                profile_id=subscriptionprofile_id, action=MemberAgencyProfileAction.SEE_PROXY_LIST
            ).pack(),
        ),
    )
    ikbuilder.row(
        InlineKeyboardButton(
            text="🔐 " + gettext("عوض کردن رمز اتصال"),
            callback_data=MemberAgencyProfileCallbackData(
                profile_id=subscriptionprofile_id, action=MemberAgencyProfileAction.PASS_CHANGE
            ).pack(),
        ),
        InlineKeyboardButton(
            text="🎁 " + gettext("هدیه به دوست"),
            callback_data=MemberAgencyProfileCallbackData(
                profile_id=subscriptionprofile_id, action=MemberAgencyProfileAction.TRANSFER_TO_ANOTHER
            ).pack(),
        ),
    )
