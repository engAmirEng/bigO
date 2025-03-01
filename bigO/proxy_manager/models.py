from solo.models import SingletonModel

from bigO.utils.models import TimeStampedModel
from django.db import models


class Config(TimeStampedModel, SingletonModel):
    sublink_header_template = models.TextField(null=True, blank=False, help_text="{{ subscription_obj }}")
    nginx_config_http_template = models.TextField(null=True, blank=False, help_text="{{ subscription_obj }}")
    nginx_config_stream_template = models.TextField(null=True, blank=False, help_text="{{ subscription_obj }}")
    xray_config_template = models.TextField(null=True, blank=False, help_text="{{ subscription_obj }}")


class Subscription(TimeStampedModel, models.Model):
    title = models.CharField(max_length=127)
    uuid = models.UUIDField(unique=True)
    user = models.ForeignKey("users.User", on_delete=models.PROTECT, null=True, blank=True)
    xray_uuid = models.UUIDField(blank=True, unique=True)
    expiry = models.DurationField(null=True, blank=True)
    upload_limit_bytes = models.PositiveBigIntegerField()
    download_limit_bytes = models.PositiveBigIntegerField()
    total_limit_bytes = models.PositiveBigIntegerField()
    description = models.TextField(max_length=4095, null=True, blank=True)
    is_active = models.BooleanField()
    # data_limit_reset_strategy
    # sub_last_user_agent
    # online_at
    # on_hold_expire_durationon_hold_expire_duration
    # on_hold_timeout
    current_download_bytes = models.PositiveBigIntegerField(default=0)
    current_upload_bytes = models.PositiveBigIntegerField(default=0)


class SubscriptionNodeUsage(TimeStampedModel, models.Model):
    # to stats db
    subscription_oid = models.PositiveIntegerField()
    node_oid = models.PositiveIntegerField()
    upload_traffic = models.PositiveSmallIntegerField()
    download_traffic = models.PositiveSmallIntegerField()


class Inbound(TimeStampedModel, models.Model):
    is_active = models.BooleanField(default=True)
    name = models.SlugField()
    inbound_template = models.TextField(help_text="{{ node_obj }}")
    link_template = models.TextField(blank=True, help_text="{{ subscription_obj }}")
    nginx_path_config = models.TextField(blank=False)

    def __str__(self):
        return f"{self.pk}-{self.name}"
