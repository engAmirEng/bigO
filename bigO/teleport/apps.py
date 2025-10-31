from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TeleportConfig(AppConfig):
    name = "bigO.teleport"
    verbose_name = _("Teleport")

    def ready(self):
        from bigO.telegram_bot.dispatchers import dp

        from .dispatchers.base import router
        from .t_middleware import CalendarMiddleware, LanguageMiddleware, TimeZoneMiddleware

        for Middleware in [LanguageMiddleware, TimeZoneMiddleware, CalendarMiddleware]:
            for k, v in router.observers.items():
                v.middleware(Middleware())

        dp.include_router(router)
