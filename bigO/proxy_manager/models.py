from solo.models import SingletonModel

from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import UniqueConstraint


class Config(TimeStampedModel, SingletonModel):
    nginx_config_http_template = models.TextField(null=True, blank=False, help_text="{{ subscription_obj }}")
    nginx_config_stream_template = models.TextField(null=True, blank=False, help_text="{{ subscription_obj }}")
    xray_config_template = models.TextField(
        null=True, blank=False, help_text="{{ node, inbound_parts, rule_parts, balancer_parts }}"
    )


class Region(TimeStampedModel, models.Model):
    name = models.SlugField()

    def __str__(self):
        return f"{self.pk}-{self.name}"


class ISP(TimeStampedModel, models.Model):
    name = models.SlugField()

    def __str__(self):
        return f"{self.pk}-{self.name}"


class OutboundGroup(TimeStampedModel, models.Model):
    name = models.SlugField(unique=True)

    def __str__(self):
        return f"{self.id}-{self.name}"


class NodeOutbound(TimeStampedModel, models.Model):
    name = models.SlugField()
    node = models.ForeignKey("node_manager.Node", on_delete=models.CASCADE, related_name="node_nodeoutbounds")
    group = models.ForeignKey(OutboundGroup, on_delete=models.CASCADE, related_name="group_nodeoutbounds")
    xray_outbound_template = models.TextField(help_text="{{ node }}")

    class Meta:
        constraints = [UniqueConstraint(fields=("name", "node"), name="unique_name_node")]

    def __str__(self):
        return f"{self.id}-{self.name}|{self.node}"


class ConnectionRule(TimeStampedModel, models.Model):
    name = models.SlugField()
    origin_region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="originregion_connectionrules")
    destination_region = models.ForeignKey(
        Region, on_delete=models.CASCADE, related_name="destinationregion_connectionrules"
    )
    xray_rules_template = models.TextField(help_text="[RuleObject], {{ node, inbound_tags }}")

    def __str__(self):
        return f"{self.pk}-{self.name}"


class Agency(TimeStampedModel, models.Model):
    name = models.SlugField()
    sublink_header_template = models.TextField(null=True, blank=False, help_text="{{ subscription_obj }}")

    def __str__(self):
        return f"{self.pk}-{self.name}"


class Subscription(TimeStampedModel, models.Model):
    connection_rule = models.ForeignKey(
        ConnectionRule,
        on_delete=models.PROTECT,
        related_name="connectionrule_subscriptions",
        null=True,
        blank=False,  # nonull
    )
    agency = models.ForeignKey(
        Agency, on_delete=models.PROTECT, related_name="agency_subscriptions", null=True, blank=False
    )  # nonull
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
    is_template = models.BooleanField(default=False)
    name = models.SlugField()
    inbound_template = models.TextField(help_text="{{ node_obj, inbound_tag, consumers_part }}")
    consumer_obj_template = models.TextField(help_text="{{ subscription_obj }}")
    link_template = models.TextField(blank=True, help_text="{{ subscription_obj }}")
    nginx_path_config = models.TextField(blank=False)

    def __str__(self):
        return f"{self.pk}-{self.name}"
