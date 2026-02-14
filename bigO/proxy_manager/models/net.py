import uuid
from types import SimpleNamespace

from simple_history.models import HistoricalRecords
from taggit.managers import TaggableManager

from bigO.utils.models import TimeStampedModel
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import UniqueConstraint

from . import typing


class RealitySpec(TimeStampedModel, models.Model):
    inbound_type = models.ForeignKey(
        "InboundType", on_delete=models.PROTECT, related_name="+", null=True
    )  # migrate null
    port = models.PositiveSmallIntegerField()
    for_ip = models.ForeignKey("node_manager.PublicIP", on_delete=models.CASCADE, related_name="+")
    dest_ip = models.ForeignKey(
        "node_manager.PublicIP", on_delete=models.CASCADE, related_name="+", blank=True, null=True
    )
    certificate_domain = models.ForeignKey("core.Domain", on_delete=models.CASCADE, related_name="+")
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return (
            f"{self.id}-{str(self.for_ip.ip)}({self.certificate_domain.name}:{str(self.dest_ip and self.dest_ip.ip)})"
        )

    def get_combo_stat(self):
        if self.dest_ip:
            address = str(self.dest_ip.ip.ip)
        else:
            address = self.certificate_domain.name
        sni = self.certificate_domain.name
        port = self.port
        return typing.ComboStat(
            **{
                "address": address,
                "port": port,
                "sni": sni,
                "domainhostheader": None,
            }
        )


class Balancer(TimeStampedModel, models.Model):
    name = models.SlugField(max_length=63)
    strategy_template = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.id}-{self.name}"


class ConnectionTunnel(TimeStampedModel, models.Model):
    source_node = models.ForeignKey("node_manager.Node", on_delete=models.CASCADE, related_name="+")
    dest_node = models.ForeignKey("node_manager.Node", on_delete=models.CASCADE, related_name="+")
    balancer = models.ForeignKey(Balancer, on_delete=models.PROTECT, related_name="+", null=True, blank=True)
    base_conn_uuid = models.UUIDField()

    class Meta:
        ordering = ["-created_at"]
        constraints = [UniqueConstraint(fields=("source_node", "dest_node"), name="unique_tunnel_between_nodes")]

    def __str__(self):
        return f"{self.id}-{self.source_node.name}->{self.dest_node.name}"

    def get_nodeinternaluser(self):
        email = f"tun{self.id}@love.com"
        return SimpleNamespace(xray_uuid=uuid.uuid5(self.base_conn_uuid, email), xray_email=lambda: email)


class ConnectionTunnelOutbound(TimeStampedModel, models.Model):
    tunnel = models.ForeignKey(ConnectionTunnel, on_delete=models.CASCADE, related_name="tunnel_outbounds")
    weight = models.PositiveSmallIntegerField()
    is_reverse = models.BooleanField(default=False)
    connector = models.ForeignKey(
        "OutboundConnector", on_delete=models.PROTECT, related_name="+", null=True
    )  # migrate null

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
                return f"{self.id}|({connector_str})▶️{self.tunnel.source_node}->{self.connector.dest_node}"
            else:
                return f"{self.id}|({connector_str}){self.tunnel.source_node}"

    def get_bridge_node(self):
        assert self.is_reverse
        return self.tunnel.dest_node

    def get_portal_node(self):
        assert self.is_reverse
        # return self.connector.dest_node ?=
        return self.tunnel.source_node

    def get_domain_for_balancer_tag(self) -> str:
        if not self.is_reverse:
            raise ValueError("this is not reverse")
        return f"tun{self.tunnel_id}.bnode{self.get_bridge_node().id}.pnode{self.get_portal_node().id}.reverse{self.id}.like.com"

    def get_proxyuser_balancer_tag(self) -> typing.ProxyUserProtocol:
        email = f"tun{self.tunnel_id}.bnode{self.get_bridge_node().id}.pnode{self.get_portal_node().id}.reverse{self.id}@love.com"
        return SimpleNamespace(xray_uuid=uuid.uuid5(self.tunnel.base_conn_uuid, email), xray_email=lambda: email)


class OutboundConnector(TimeStampedModel, models.Model):
    is_managed = models.BooleanField(default=False)  # todo
    outbound_type = models.ForeignKey("OutboundType", on_delete=models.CASCADE, related_name="variants")
    inbound_spec = models.ForeignKey("InboundSpec", on_delete=models.CASCADE, related_name="+", null=True, blank=True)
    dest_node = models.ForeignKey(
        "node_manager.Node", on_delete=models.CASCADE, related_name="+", null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            UniqueConstraint(
                fields=("outbound_type", "inbound_spec"), name="unique_outboundtype_inbound_spec_outboundconnector"
            )
        ]

    def __str__(self):
        if self.inbound_spec:
            o = f"({self.outbound_type.name}({self.inbound_spec.id}))"
        else:
            o = f"({self.outbound_type.name}(-))"
        dest_node_display = "?"
        if self.dest_node:
            first_ip = self.dest_node.node_nodepublicips.first()
            dest_node_display = f"{first_ip.ip.get_region_display() if first_ip else ''}{self.dest_node.name}"
        return f"{self.id}-{o}->{dest_node_display}"


class OutboundType(TimeStampedModel, models.Model):
    name = models.SlugField(unique=True, max_length=127)
    to_inbound_type = models.ForeignKey(
        "InboundType",
        on_delete=models.CASCADE,
        related_name="+",
        null=True,
        blank=True,
    )
    xray_outbound_template = models.TextField(
        help_text="{{ source_node, dest_node, tag, nodeinternaluser, combo_stat: {'address', 'port', 'sni', 'domainhostheader'} }}"
    )
    history = HistoricalRecords()

    def __str__(self):
        res = f"{self.id}-{self.name}"
        if self.to_inbound_type:
            res += f"({self.to_inbound_type.name})"
        else:
            res += f"(-)"
        return res


class LocalTunnelPort(TimeStampedModel, models.Model):
    tunnel = models.ForeignKey(ConnectionTunnel, on_delete=models.CASCADE, related_name="tunnel_localtunnelports")
    local_port = models.PositiveIntegerField()
    dest_port = models.PositiveIntegerField()
    dest_node = models.ForeignKey(
        "node_manager.Node", on_delete=models.CASCADE, related_name="+", null=True, blank=True
    )

    def clean(self):
        super().clean()
        similar_qs = LocalTunnelPort.objects.filter(tunnel=self.tunnel, local_port=self.local_port)
        if self.id:
            similar_qs = similar_qs.exclude(id=self.id)
        if similar_obj := similar_qs.first():
            raise ValidationError(f"{self.local_port} port is used in {similar_obj.tunnel_id=}")
