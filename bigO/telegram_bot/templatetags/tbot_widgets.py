from asgiref.sync import async_to_sync

from django import template
from django.contrib import messages
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

from ..utils import get_message

register = template.Library()


@register.simple_tag(takes_context=False)
def progress_bar(current: int, total: int, width: int = 20) -> str:
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    percent = (current / total) * 100
    return f"[{bar}] {percent:5.1f}%"


@register.simple_tag(takes_context=True)
def trender_messages(context, template_name: str):
    state = context["state"]
    message_list = async_to_sync(get_message)(state=state)
    return mark_safe(
        render_to_string(
            template_name=template_name,
            context={"messages": message_list, "DEFAULT_MESSAGE_LEVELS": messages.DEFAULT_LEVELS},
        )
    )
