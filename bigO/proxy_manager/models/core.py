from solo.models import SingletonModel

from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import UniqueConstraint


class Config(TimeStampedModel, SingletonModel):
    nginx_config_http_template = models.TextField(null=True, blank=False, help_text="{{ node_obj }}")
    nginx_config_stream_template = models.TextField(null=True, blank=False, help_text="{{ node_obj }}")
    xray_config_template = models.TextField(
        null=True, blank=False, help_text="{{ node, inbound_parts, rule_parts, balancer_parts }}"
    )
    geosite = models.ForeignKey(
        "node_manager.ProgramVersion",
        related_name="geosite_xrayconfig",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    geoip = models.ForeignKey(
        "node_manager.ProgramVersion", related_name="geoip_xrayconfig", on_delete=models.PROTECT, null=True, blank=True
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
        ordering = ["-created_at"]
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


class InboundType(TimeStampedModel, models.Model):
    is_active = models.BooleanField(default=True)
    is_template = models.BooleanField(default=False)
    name = models.SlugField()
    inbound_template = models.TextField(help_text="{{ node_obj, inbound_tag, consumers_part }}")
    consumer_obj_template = models.TextField(help_text="{{ subscriptionperiod_obj }}")
    link_template = models.TextField(blank=True, null=True, help_text="{{ subscriptionperiod_obj }}")
    nginx_path_config = models.TextField(blank=True, null=True)
    haproxy_backend = models.TextField(blank=True, null=True)
    haproxy_matcher_80 = models.TextField(blank=True, null=True)
    haproxy_matcher_443 = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.pk}-{self.name}"


# class InboundTypeFallback(TimeStampedModel, models.Model):
#     ref_type = models.ForeignKey(InboundType, on_delete=models.PROTECT, related_name="reftype_inboundtypefallback")
#     dest_type = models.ForeignKey(InboundType, on_delete=models.PROTECT, related_name="desttype_inboundtypefallback")

# class InboundGroup(TimeStampedModel, models.Model):
#     template = models.ForeignKey
#     inbound_groups = models.ManyToManyField("self")


class SubscriptionNodeUsage(TimeStampedModel, models.Model):
    # to stats db
    subscription_oid = models.PositiveIntegerField()
    node_oid = models.PositiveIntegerField()
    upload_traffic = models.PositiveSmallIntegerField()
    download_traffic = models.PositiveSmallIntegerField()
