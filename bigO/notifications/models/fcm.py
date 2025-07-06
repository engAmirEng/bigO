from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import Q, UniqueConstraint


class FCM(TimeStampedModel, models.Model):
    user_device = models.ForeignKey("core.UserDevice", on_delete=models.CASCADE, related_name="fcm_set")
    account = models.ForeignKey("NotificationAccount", on_delete=models.CASCADE, related_name="fcm_set")
    token = models.TextField()

    class Meta:
        verbose_name = "FCM"
        constraints = [
            UniqueConstraint(
                fields=("user_device", "account"),
                name="unique_for_device_and_account",
            )
        ]

    def save(self, *args, **kwargs):
        from .base import BaseNotificationProvider

        assert self.account.type == BaseNotificationProvider.Type.FCM
        return super().save(*args, **kwargs)
