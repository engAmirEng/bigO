from bigO.telegram_bot import dispatchers
from bigO.telegram_bot.webhook import get_webhook_view
from bigO.utils.decorators import csrf_exempt
from django.urls import path

from . import settings

app_name = "telegram_bot"

urlpatterns = [
    path(
        f"{settings.TELEGRAM_WEBHOOK_URL_PREFIX}/<path:url_specifier>/",
        csrf_exempt(get_webhook_view(dispatchers.dp)),
        name="webhook",
    ),
]
