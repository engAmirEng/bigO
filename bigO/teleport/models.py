from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import Q, UniqueConstraint


class Panel(TimeStampedModel, models.Model):
    is_active = models.BooleanField(default=True)
    agency = models.ForeignKey("proxy_manager.Agency", on_delete=models.CASCADE, related_name="+")
    bot = models.ForeignKey("telegram_bot.TelegramBot", on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [UniqueConstraint(fields=("bot",), condition=Q(is_active=True), name="unique_bot_panel")]
