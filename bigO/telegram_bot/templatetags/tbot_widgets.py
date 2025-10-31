from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=False)
def progress_bar(current: int, total: int, width: int = 20) -> str:
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    percent = (current / total) * 100
    return f"[{bar}] {percent:5.1f}%"
