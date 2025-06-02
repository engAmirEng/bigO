import uuid

import django_jsonform.models.fields
from solo.models import SingletonModel

from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import UniqueConstraint

from .. import typing


class Config(TimeStampedModel, SingletonModel):
    nginx_config_http_template = models.TextField(
        null=True, blank=False, help_text="{{ node_obj, xray_path_matchers }}"
    )
    nginx_config_stream_template = models.TextField(null=True, blank=False, help_text="{{ node_obj }}")
    xray_config_template = models.TextField(
        null=True, blank=False, help_text="{{ node, inbound_parts, rule_parts, balancer_parts, outbound_parts }}"
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


class NodeOutbound(TimeStampedModel, models.Model):
    name = models.SlugField()
    balancer_allocation_str = models.CharField(
        max_length=255, validators=[], help_text="balancertag1:weght,balancertag1:weght"
    )
    node = models.ForeignKey("node_manager.Node", on_delete=models.CASCADE, related_name="node_nodeoutbounds")
    rule = models.ForeignKey("ConnectionRule", on_delete=models.CASCADE, related_name="rule_nodeoutbounds")
    to_inbound_type = models.ForeignKey(
        "InboundType", on_delete=models.CASCADE, related_name="toinboundtype_nodeoutbounds", null=True, blank=True
    )
    xray_outbound_template = models.TextField(
        help_text="{{ node, tag, nodeinternaluser, combo_stat: {'address', 'port', 'sni', 'domainhostheader', 'touch_node'} }}"
    )
    inbound_spec = models.ForeignKey(
        "InboundSpec",
        on_delete=models.PROTECT,
        related_name="inboundspec_nodeoutbounds",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [UniqueConstraint(fields=("name", "node", "rule"), name="unique_name_node_rule_nodeoutbound")]

    def __str__(self):
        if self.to_inbound_type:
            return f"{self.id}-{self.to_inbound_type.name}|{self.node}"
        return f"{self.id}|{self.node}"

    def get_balancer_allocations(self) -> list[tuple[str, int]]:
        res = []
        parts = self.balancer_allocation_str.split(",")
        for part in parts:
            balancer_name, weight = part.split(":")
            res.append((balancer_name, int(weight)))
        return res


class ConnectionRule(TimeStampedModel, models.Model):
    name = models.SlugField()
    origin_region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="originregion_connectionrules")
    destination_region = models.ForeignKey(
        Region, on_delete=models.CASCADE, related_name="destinationregion_connectionrules"
    )
    xray_rules_template = models.TextField(help_text="[RuleObject], {{ node, subscriptionperiods, inbound_tags }}")

    inboundcombogroup = models.ForeignKey(
        "InboundComboGroup",
        on_delete=models.PROTECT,
        related_name="inboundcombogroup_connectionrules",
        null=True,
        blank=True,
    )
    inbound_remarks_prefix = models.CharField(max_length=255, null=True, blank=True)
    INBOUND_CHOOSE_RULE_SCHEMA = typing.InboundChooseRuleSchema.model_json_schema()
    inbound_choose_rule = django_jsonform.models.fields.JSONField(
        schema=INBOUND_CHOOSE_RULE_SCHEMA, null=True, blank=True
    )

    def __str__(self):
        return f"{self.pk}-{self.name}"


class ConnectionRuleInboundSpec(TimeStampedModel, models.Model):
    key = models.CharField(max_length=63)
    rule = models.ForeignKey(ConnectionRule, on_delete=models.CASCADE, related_name="rule_connectionruleinboundspecs")
    spec = models.ForeignKey("InboundSpec", on_delete=models.CASCADE, related_name="+")
    weight = models.PositiveSmallIntegerField(default=0)


class InternalUser(TimeStampedModel, models.Model):
    connection_rule = models.ForeignKey(ConnectionRule, on_delete=models.CASCADE, related_name="+")
    node = models.ForeignKey("node_manager.Node", on_delete=models.CASCADE, related_name="+")
    xray_uuid = models.UUIDField(blank=True, unique=True)

    is_active = models.BooleanField(default=True)

    first_usage_at = models.DateTimeField(null=True, blank=True)
    last_usage_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [UniqueConstraint(fields=("connection_rule", "node"), name="unique_connection_rule_ip")]

    def xray_email(self):
        return f"rule{self.connection_rule_id}.node{self.node_id}@love.com"

    @classmethod
    def init_for_node(cls, node, connection_rule):
        obj = cls()
        obj.node = node
        obj.xray_uuid = uuid.uuid4()
        obj.connection_rule = connection_rule
        obj.is_active = True
        obj.save()
        return obj


class InboundType(TimeStampedModel, models.Model):
    is_active = models.BooleanField(default=True)
    is_template = models.BooleanField(default=False)
    name = models.SlugField()
    inbound_template = models.TextField(help_text="{{ node_obj, inbound_tag, consumers_part }}")
    consumer_obj_template = models.TextField(help_text="{{ subscriptionperiod_obj }}")
    link_template = models.TextField(
        blank=True,
        null=True,
        help_text="{{ subscriptionperiod_obj, connection_rule, combo_stat: {'address', 'port', 'sni', 'domainhostheader', 'touch_node'}, remark_prefix }}",
    )
    nginx_path_config = models.TextField(blank=True, null=True, help_text="{{ node_obj }}")
    haproxy_backend = models.TextField(blank=True, null=True, help_text="{{ node_obj }}")
    haproxy_matcher_80 = models.TextField(blank=True, null=True, help_text="{{ node_obj }}")
    haproxy_matcher_443 = models.TextField(blank=True, null=True, help_text="{{ node_obj }}")

    def __str__(self):
        return f"{self.pk}-{self.name}"


class SubscriptionNodeUsage(TimeStampedModel, models.Model):
    # to stats db
    subscription_oid = models.PositiveIntegerField()
    node_oid = models.PositiveIntegerField()
    upload_traffic = models.PositiveSmallIntegerField()
    download_traffic = models.PositiveSmallIntegerField()
