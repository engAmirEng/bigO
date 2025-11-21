import aiogram
from asgiref.sync import async_to_sync

from django import template
from django.contrib import messages
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from ..dispatchers import get_dispatch_query, QueryPathName
from bigO.proxy_manager import models as proxy_manager_models

register = template.Library()


@register.simple_tag(takes_context=False)
def member_profile_detail_link(bot_username: str, subscription_profile: proxy_manager_models.SubscriptionProfile):
    link = get_dispatch_query(
        bot_username=bot_username, pathname=QueryPathName.MEMBER_PROFILE_DETAIL, id=subscription_profile.id
    )
    return link
