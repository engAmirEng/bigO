import netfields
from rest_framework_api_key.models import AbstractAPIKey

import django.template.loader
from bigO.utils.models import TimeStampedModel
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import UniqueConstraint, F, CheckConstraint


class Node(TimeStampedModel, models.Model):
    name = models.CharField(max_length=255)
    is_tunable = models.BooleanField(default=True, help_text="can tuns be created on it?")


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
                raise ValidationError("{0} overlaps with {1}".format(self.ip_range, ". ".join([f"{i}-{i.ip_range}" for i in overlapsed_network_qs])))


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
    custom_toml_config_template = models.TextField(null=True, blank=True)

    class EasyTierNodeQuerySet(models.QuerySet):
        def ann_create_tun(self):
            return self.annotate(create_tun=F("node__is_tunable"))
    objects = EasyTierNodeQuerySet.as_manager()

    def get_toml_config(self):
        context = {"easytier_node_obj": self}
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

    def clean(self):
        super().clean()
        if self.peer_listener_id and self.node_id:
            if self.peer_listener.node == self.node:
                raise ValidationError("peer and node cannot ba the same")
        if self.peer_public_ip_id and self.peer_listener_id:
            if not self.peer_listener.node.node.node_nodepublicips.filter(id=self.peer_public_ip.id).exists():
                raise ValidationError(f"{self.peer_public_ip} not one of peer node public ips.")


class GostClientNode(TimeStampedModel):
    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="gostservers",
    )
