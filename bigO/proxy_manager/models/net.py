import uuid
from types import SimpleNamespace

from simple_history.models import HistoricalRecords
from taggit.managers import TaggableManager

from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import UniqueConstraint

from . import typing


class RealitySpec(TimeStampedModel, models.Model):
    port = models.PositiveSmallIntegerField()
    for_ip = models.ForeignKey("node_manager.PublicIP", on_delete=models.CASCADE, related_name="+")
    dest_ip = models.ForeignKey(
        "node_manager.PublicIP", on_delete=models.CASCADE, related_name="+", blank=True, null=True
    )
    certificate_domain = models.ForeignKey("core.Domain", on_delete=models.CASCADE, related_name="+")
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.id}-{self.certificate_domain.name}"


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

    def get_domain_for_balancer_tag(self) -> str:
        if not self.is_reverse:
            raise ValueError("this is not reverse")
        return f"tun{self.tunnel_id}.bnode{self.tunnel.dest_node_id}.pnode{self.tunnel.source_node_id}.reverse{self.id}.like.com"

    def get_proxyuser_balancer_tag(self) -> typing.ProxyUserProtocol:
        email = f"tun{self.tunnel_id}.bnode{self.tunnel.dest_node_id}.pnode{self.tunnel.source_node_id}.reverse{self.id}@love.com"
        return SimpleNamespace(xray_uuid=uuid.uuid5(self.tunnel.base_conn_uuid, email), xray_email=lambda: email)


class OutboundConnector(TimeStampedModel, models.Model):
    is_managed = models.BooleanField(default=False)  # todo
    outbound_type = models.ForeignKey("OutboundType", on_delete=models.CASCADE, related_name="variants")
    inbound_spec = models.ForeignKey("InboundSpec", on_delete=models.CASCADE, related_name="+", null=True, blank=True)
    dest_node = models.ForeignKey(
        "node_manager.Node", on_delete=models.CASCADE, related_name="+", null=True, blank=True
    )


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
        help_text="{{ source_node, dest_node, tag, nodeinternaluser, combo_stat: {'address', 'port', 'sni', 'domainhostheader', 'touch_node'} }}"
    )
    history = HistoricalRecords()


class LocalTunnelPort(TimeStampedModel, models.Model):
    source_node = models.ForeignKey("node_manager.Node", on_delete=models.CASCADE, related_name="+")
    tunnel = models.ForeignKey(ConnectionTunnel, on_delete=models.CASCADE)
    local_port = models.PositiveIntegerField()
    dest_port = models.PositiveIntegerField()
