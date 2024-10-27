import logging
from typing import Self

import netfields
from rest_framework_api_key.models import AbstractAPIKey

import django.template.loader
from bigO.utils.models import TimeStampedModel
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, UniqueConstraint

logger = logging.getLogger(__name__)


class Node(TimeStampedModel, models.Model):
    name = models.CharField(max_length=255)
    is_tunable = models.BooleanField(default=True, help_text="can tuns be created on it?")

    class NodeQuerySet(models.QuerySet):
        def support_ipv6(self):
            return self.filter(node_nodepublicips__ip__ip__family=6)

    objects = NodeQuerySet.as_manager()

    def get_support_ipv6(self):
        return Node.objects.filter(id=self.id).support_ipv6().exists()


class NodeAPIKey(TimeStampedModel, AbstractAPIKey):
    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="apikeys",
    )


class PublicIP(TimeStampedModel):
    name = models.CharField(max_length=255, null=True, blank=True)
    ip = netfields.InetAddressField(unique=True)
    is_cdn = models.BooleanField(default=False)


class NodePublicIP(TimeStampedModel):
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="node_nodepublicips")
    ip = models.ForeignKey(PublicIP, on_delete=models.CASCADE, related_name="ip_nodepublicips")


class CustomConfigTemplate(TimeStampedModel, models.Model):
    class TypeChoices(models.TextChoices):
        NGINX = "nginx"
        GOST = "gost"

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=15, choices=TypeChoices.choices)
    template = models.TextField()


class NodeCustomConfigTemplate(TimeStampedModel):
    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="node_customconfigtemplates",
    )
    config_template = models.ForeignKey(
        CustomConfigTemplate, on_delete=models.CASCADE, related_name="nodecustomconfigtemplates"
    )

    class Meta:
        constraints = [UniqueConstraint(fields=("node", "config_template"), name="unique_node_config_template")]


class EasyTierNetwork(TimeStampedModel):
    network_name = models.CharField(max_length=255, unique=True)
    network_secret = models.CharField(max_length=255)
    ip_range = netfields.CidrAddressField()

    def clean(self):
        if self.ip_range:
            overlapsed_network_qs = EasyTierNetwork.objects.filter(ip_range__net_overlaps=self.ip_range)
            if self.id:
                overlapsed_network_qs = overlapsed_network_qs.exclude(id=self.id)
            if overlapsed_network_qs.exists():
                raise ValidationError(
                    "{} overlaps with {}".format(
                        self.ip_range, ". ".join([f"{i}-{i.ip_range}" for i in overlapsed_network_qs])
                    )
                )


class EasyTierNode(TimeStampedModel):
    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="node_easytiernods",
    )
    external_node = models.CharField(
        max_length=255, null=True, blank=True, help_text="tcp://public.easytier.top:11010"
    )
    network = models.ForeignKey(EasyTierNetwork, on_delete=models.CASCADE, related_name="network_easytiernodes")
    ipv4 = netfields.InetAddressField(
        null=True, blank=True, help_text="this is a stational entity"
    )  # stational entity
    custom_toml_config_template = models.TextField(null=True, blank=True)

    class EasyTierNodeQuerySet(models.QuerySet):
        def ann_can_create_tun(self):
            return self.annotate(can_create_tun=F("node__is_tunable"))

        def can_create_tun(self):
            return self.ann_can_create_tun().filter(can_create_tun=True)

    objects = EasyTierNodeQuerySet.as_manager()

    def get_can_create_tun(self):
        return EasyTierNode.objects.filter(id=self.id).can_create_tun().exists()

    @transaction.atomic
    def get_toml_config(self):
        ipv4 = None
        if self.get_can_create_tun():
            used_ipv4s = (
                EasyTierNode.objects.filter(network=self.network, ipv4__isnull=False)
                .exclude(id=self.id)
                .values_list("ipv4", flat=True)
            )
            used_ipv4s = [i.ip for i in used_ipv4s]
            if self.ipv4 and self.ipv4 in self.network.ip_range and self.ipv4 not in used_ipv4s:
                ipv4 = self.ipv4
            else:
                for i in self.network.ip_range.hosts():
                    if i not in used_ipv4s:
                        ipv4 = i
                        break
                else:
                    logger.critical(f"no available ipv4 found be assigned to {self}")
        if ipv4 and self.ipv4 != ipv4:
            self.ipv4 = ipv4
            self.save()

        node_peers = []
        peers = []
        kept_current_nodepeers = []
        new_nodepeers = []
        current_nodepeers_qs = self.node_nodepeers.all()
        for network_easytiernode in self.network.network_easytiernodes.exclude(id=self.id).exclude(ipv4__isnull=True):
            nodepublicips_qs = network_easytiernode.node.node_nodepublicips.all()
            if not self.node.get_support_ipv6():
                nodepublicips_qs = nodepublicips_qs.exclude(ip__ip__family=6)
            for nodepublicip in nodepublicips_qs:
                for nodelistener in network_easytiernode.node_nodelisteners.all():
                    peer = EasyTierNodePeer()
                    peer.node = self
                    peer.peer_listener = nodelistener
                    peer.peer_public_ip = nodepublicip
                    node_peers.append(peer)

            for i in node_peers:
                for j in current_nodepeers_qs:
                    if not j.does_need_recreation_to(i):
                        kept_current_nodepeers.append(j)
                        break
                else:
                    new_nodepeers.append(i)
        current_nodepeers_qs.exclude(id__in=[i.id for i in kept_current_nodepeers]).delete()
        for i in new_nodepeers:
            i.save()
        for nodepeer in node_peers:
            peer = f"{nodepeer.peer_listener.protocol}://{nodepeer.peer_public_ip.ip.ip}:{nodepeer.peer_listener.port}"
            peers.append(peer)

        context = {"easytier_node_obj": self, "ipv4": ipv4, "external_node": self.external_node, "peers": peers}
        if self.custom_toml_config_template:
            template = django.template.Template(self.custom_toml_config_template)
            result = template.render(context=django.template.Context(context))
        else:
            template = django.template.loader.get_template("node_manager/configs/easytier.toml")
            result = template.render(context)
        return result


class EasyTierNodeListener(TimeStampedModel):
    class ProtocolChoices(models.TextChoices):
        TCP = "tcp"
        UDP = "udp"
        WS = "ws"
        WSS = "wss"

    node = models.ForeignKey(EasyTierNode, on_delete=models.CASCADE, related_name="node_nodelisteners")
    protocol = models.CharField(max_length=15, choices=ProtocolChoices.choices)
    port = models.PositiveSmallIntegerField()  # stational entity


class EasyTierNodePeer(TimeStampedModel):
    """this is the stational entity and not persisted"""

    node = models.ForeignKey(EasyTierNode, on_delete=models.CASCADE, related_name="node_nodepeers")
    peer_listener = models.ForeignKey(
        EasyTierNodeListener, on_delete=models.CASCADE, related_name="peerlistener_nodepeers"
    )
    peer_public_ip = models.ForeignKey(NodePublicIP, on_delete=models.CASCADE, related_name="peerpublicip_nodepeers")

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=("node", "peer_listener", "peer_public_ip"), name="unique_peer_listener_peer_public_ip_per_node"
            )
        ]

    def clean(self):
        super().clean()
        if self.peer_listener_id and self.node_id:
            if self.peer_listener.node == self.node:
                raise ValidationError("peer and node cannot ba the same")
        if self.peer_public_ip_id and self.peer_listener_id:
            if not self.peer_listener.node.node.node_nodepublicips.filter(id=self.peer_public_ip.id).exists():
                raise ValidationError(f"{self.peer_public_ip} not one of peer node public ips.")

    def does_need_recreation_to(self, other: Self):
        return not (
            self.node == other.node
            and self.peer_listener_id == other.peer_listener_id
            and self.peer_public_ip == other.peer_public_ip
        )


class GostClientNode(TimeStampedModel):
    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="gostservers",
    )
