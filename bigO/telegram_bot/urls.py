from bigO.telegram_bot import dispatchers
from bigO.telegram_bot.webhook import get_webhook_view
from bigO.utils.decorators import csrf_exempt
from . import settings
from django.urls import path

urlpatterns = [
    path(
        f"{settings.TELEGRAM_WEBHOOK_URL_PREFIX}/<path:url_specifier>/",
        csrf_exempt(get_webhook_view(dispatchers.dp)),
    ),
]
