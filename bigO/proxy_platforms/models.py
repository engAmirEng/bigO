from bigO.utils.models import TimeStampedModel
from django.db import models


class Subscription(TimeStampedModel, models.Model):
    user = models.ForeignKey("users.User", on_delete=models.PROTECT)
    xray_uuid = models.UUIDField()
    expiry = models.DurationField()
    data_limit_bytes = models.PositiveBigIntegerField()
    description = models.TextField(max_length=4095)
    is_active = models.BooleanField()
    # data_limit_reset_strategy
    # sub_last_user_agent
    # online_at
    # on_hold_expire_durationon_hold_expire_duration
    # on_hold_timeout


class SubscriptionNodeUsage(TimeStampedModel, models.Model):
    # to stats db
    subscription_oid = models.PositiveIntegerField()
    node_oid = models.PositiveIntegerField()
    upload_traffic = models.PositiveSmallIntegerField()
    download_traffic = models.PositiveSmallIntegerField()
