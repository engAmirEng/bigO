from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UserBotConfig(AppConfig):
    name = "bigO.user_bot"
    verbose_name = _("User Bot")

    def ready(self):
        from bigO.telegram_bot.dispatchers import dp

        from .tbot_communicator.dispatchers import router

        dp.include_router(router)
