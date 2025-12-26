from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import Q, UniqueConstraint


class Panel(TimeStampedModel, models.Model):
    is_active = models.BooleanField(default=True)
    agency = models.ForeignKey("proxy_manager.Agency", on_delete=models.CASCADE, related_name="agency_teleportpanels")
    bot = models.ForeignKey("telegram_bot.TelegramBot", on_delete=models.CASCADE, related_name="+")
    toturial_content = models.TextField(null=True, blank=True)
    toturial_message = models.ForeignKey(
        "telegram_bot.TelegramMessage", on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    member_subscription_notif = models.BooleanField(default=True)

    class Meta:
        constraints = [UniqueConstraint(fields=("bot",), condition=Q(is_active=True), name="unique_bot_panel")]
