import uuid
from decimal import Decimal
from types import SimpleNamespace

import django_jsonform.models.fields
from simple_history.models import HistoricalRecords
from solo.models import SingletonModel

from bigO.utils.models import TimeStampedModel
from django.core.exceptions import ValidationError
from django.core.validators import int_list_validator
from django.db import models
from django.db.models import OuterRef, Subquery, Sum, UniqueConstraint
from django.db.models.functions import Coalesce

from .. import typing


class Config(TimeStampedModel, SingletonModel):
    sublink_debug = models.BooleanField(default=False, help_text="should be off, will reveal systems fingerprint")
    nginx_config_http_template = models.TextField(
        null=True, blank=False, help_text="{{ node_obj, xray_path_matchers }}"
    )
    nginx_config_stream_template = models.TextField(null=True, blank=False, help_text="{{ node_obj }}")
    haproxy_config_template = models.TextField(
        null=True,
        blank=True,
        help_text="{{ node_obj, xray_backends_part, xray_80_matchers_par, xray_443_matchers_part }}",
    )
    xray_config_template = models.TextField(
        null=True,
        blank=False,
        help_text="{{ node, inbound_parts, rule_parts, balancer_parts, outbound_parts, outbound_tags, portal_parts, bridge_parts }}",
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
    tunnel_dest_ports = models.CharField(max_length=255, validators=[int_list_validator], null=True, blank=True)
    admin_panel_influx_delays = models.BooleanField(default=True)
    usage_correction_factor = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    history = HistoricalRecords()


class Region(TimeStampedModel, models.Model):
    name = models.SlugField()
    short_display = models.CharField(max_length=7, null=True, blank=True)

    def __str__(self):
        return f"{self.pk}-{self.short_display or ''}{self.name}"


class ISP(TimeStampedModel, models.Model):
    name = models.SlugField()

    def __str__(self):
        return f"{self.pk}-{self.name}"


class DNS:
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="+")
    nodes = models.ManyToManyField("node_manager.Node")

class ConnectionRuleOutbound(TimeStampedModel, models.Model):
    rule = models.ForeignKey("ConnectionRule", on_delete=models.CASCADE, related_name="rule_outbounds")
    balancer_allocation_str = models.CharField(
        max_length=255, validators=[], help_text="balancertag1:weght,balancertag1:weght"
    )
    is_reverse = models.BooleanField(default=False)
    connector = models.ForeignKey("OutboundConnector", on_delete=models.PROTECT, related_name="+")
    apply_node = models.ForeignKey("node_manager.Node", on_delete=models.CASCADE, related_name="+")
    base_conn_uuid = models.UUIDField()

    def str_id(self):
        return str(self.id)

    def __str__(self):
        if self.connector.inbound_spec:
            o = f"({self.connector.outbound_type.name}({self.connector.inbound_spec.id}))"
        else:
            o = f"({self.connector.outbound_type.name}(-))"
        connector_str = f"{o}->{self.connector.dest_node.name if self.connector.dest_node else '?'}"
        if self.is_reverse:
            try:
                portal_node_str = self.get_portal_node()
            except Exception as e:
                portal_node_str = f"error-{str(e)}"
            try:
                bridge_node_str = self.get_bridge_node()
            except Exception as e:
                bridge_node_str = f"error-{str(e)}"
            return f"{self.id}|({connector_str})◀️{portal_node_str}->{bridge_node_str}"
        else:
            if self.connector.dest_node:
                return f"{self.id}|({connector_str})▶️{self.apply_node}->{self.connector.dest_node}"
            else:
                return f"{self.id}|({connector_str}){self.apply_node}"

    def clean(self):
        try:
            self.get_balancer_allocations()
        except Exception as e:
            raise ValidationError(f"balancer_allocation_str is not valid, {str(e)}")

    def get_bridge_node(self):
        assert self.is_reverse
        return self.apply_node

    def get_portal_node(self):
        assert self.is_reverse
        return self.connector.dest_node

    def get_balancer_allocations(self) -> list[tuple[str, Decimal]]:
        res = []
        parts = self.balancer_allocation_str.split(",")
        for part in parts:
            balancer_name, weight = part.split(":")
            res.append((balancer_name, Decimal(weight)))
        return res

    def get_domain_for_balancer_tag(self, balancer_tag: str) -> str:
        return f"rule{self.rule_id}.bnode{self.get_bridge_node().id}.pnode{self.get_portal_node().id}.reverse{self.id}.{balancer_tag}.like.com"

    def get_proxyuser_balancer_tag(self, balancer_tag: str) -> typing.ProxyUserProtocol:
        email = f"rule{self.rule_id}.bnode{self.get_bridge_node().id}.pnode{self.get_portal_node().id}.reverse{self.id}.{balancer_tag}@love.com"
        return SimpleNamespace(xray_uuid=uuid.uuid5(self.base_conn_uuid, email), xray_email=lambda: email)


class ConnectionRule(TimeStampedModel, models.Model):
    class ConnectionRuleQuerySet(models.QuerySet):
        def ann_periods_count(self):
            from ..models import SubscriptionPlan

            qs = SubscriptionPlan.objects.filter(connection_rule=OuterRef("id")).ann_periods_count()
            return self.annotate(
                periods_count=Coalesce(
                    Subquery(
                        qs.order_by()
                        .values("connection_rule")
                        .annotate(periods_count=Sum("periods_count"))
                        .values("periods_count")
                    ),
                    0,
                ),
                alive_periods_count=Coalesce(
                    Subquery(
                        qs.order_by()
                        .values("connection_rule")
                        .annotate(alive_periods_count=Sum("alive_periods_count"))
                        .values("alive_periods_count")
                    ),
                    0,
                ),
            )

    name = models.SlugField()
    origin_region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="originregion_connectionrules")
    destination_region = models.ForeignKey(
        Region, on_delete=models.CASCADE, related_name="destinationregion_connectionrules"
    )
    xray_rules_template = models.TextField(help_text="[RuleObject], {{ node, subscriptionperiods, inbound_tags }}")
    inbound_remarks_prefix = models.CharField(max_length=255, null=True, blank=True)
    INBOUND_CHOOSE_RULE_SCHEMA = typing.InboundChooseRuleSchema.model_json_schema()
    inbound_choose_rule = django_jsonform.models.fields.JSONField(
        schema=INBOUND_CHOOSE_RULE_SCHEMA, null=True, blank=True
    )

    history = HistoricalRecords()

    objects = ConnectionRuleQuerySet.as_manager()

    def __str__(self):
        return f"{self.pk}-{self.name}"


class ConnectionRuleBalancer(TimeStampedModel, models.Model):
    name = models.SlugField(max_length=63)
    connection_rule = models.ForeignKey(ConnectionRule, on_delete=models.CASCADE, related_name="balancers")
    strategy_template = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=("name", "connection_rule"),
                name="balancer_unique_name_connection_rule",
                violation_error_message="already exists with this name for this connection rule",
            )
        ]


class ConnectionRuleInboundSpec(TimeStampedModel, models.Model):
    key = models.CharField(max_length=63)
    rule = models.ForeignKey(ConnectionRule, on_delete=models.CASCADE, related_name="rule_connectionruleinboundspecs")
    spec = models.ForeignKey(
        "InboundSpec", on_delete=models.CASCADE, related_name="+", null=True, blank=True, help_text="deprecated"
    )
    connector = models.ForeignKey(
        "OutboundConnector", on_delete=models.CASCADE, related_name="+", null=True, blank=True
    )  # migrate null
    weight = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        if self.spec:
            return super().__str__()
        if self.connector.inbound_spec:
            o = f"({self.connector.outbound_type.name}({self.connector.inbound_spec.id}))"
        else:
            o = f"({self.connector.outbound_type.name}(-))"
        connector_str = f"{o}->{self.connector.dest_node.name if self.connector.dest_node else '?'}"
        if self.connector.dest_node:
            return f"{self.id}|({connector_str})▶️{self.rule.name}->{self.connector.dest_node}"
        else:
            return f"{self.id}|({connector_str})▶️{self.rule.name}"

    def clean(self):
        if self.weight > 0 and self.connector and self.spec:
            raise ValidationError("either connector or spec")
        if self.weight > 0 and not self.connector and not self.spec:
            raise ValidationError("either connector or spec")
        if self.connector:
            if self.weight > 0 and self.connector.inbound_spec is None:
                raise ValidationError("connector.inbound_spec is None")
            if self.weight > 0 and self.connector.outbound_type.to_inbound_type is None:
                raise ValidationError("connector.outbound_type.to_inbound_type is None")


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
    inbound_template = models.TextField(
        help_text="{{ node_obj, inbound_tag, consumers_part, combo_stat: {'address', 'port', 'sni', 'domainhostheader'} }}"
    )
    consumer_obj_template = models.TextField(help_text="{{ subscriptionperiod_obj }}")
    link_template = models.TextField(
        blank=True,
        null=True,
        help_text="{{ subscriptionperiod_obj, connection_rule, combo_stat: {'address', 'port', 'sni', 'domainhostheader'}, remark_prefix }}",
    )
    nginx_path_config = models.TextField(
        blank=True,
        null=True,
        help_text="{{ node_obj, inbound_tag, combo_stat: {'address', 'port', 'sni', 'domainhostheader'} }}",
    )
    haproxy_backend = models.TextField(
        blank=True,
        null=True,
        help_text="{{ node_obj, inbound_tag, combo_stat: {'address', 'port', 'sni', 'domainhostheader'} }}",
    )
    haproxy_matcher_80 = models.TextField(
        blank=True,
        null=True,
        help_text="{{ node_obj, inbound_tag, combo_stat: {'address', 'port', 'sni', 'domainhostheader'} }}",
    )
    haproxy_matcher_443 = models.TextField(
        blank=True,
        null=True,
        help_text="{{ node_obj, inbound_tag, combo_stat: {'address', 'port', 'sni', 'domainhostheader'} }}",
    )

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.pk}-{self.name}"


class SubscriptionNodeUsage(TimeStampedModel, models.Model):
    # to stats db
    subscription_oid = models.PositiveIntegerField()
    node_oid = models.PositiveIntegerField()
    upload_traffic = models.PositiveSmallIntegerField()
    download_traffic = models.PositiveSmallIntegerField()
