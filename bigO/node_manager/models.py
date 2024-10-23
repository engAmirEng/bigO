from rest_framework_api_key.models import AbstractAPIKey

from bigO.utils.models import TimeStampedModel
from django.core.exceptions import ValidationError
from django.db import models


class Node(TimeStampedModel, models.Model):
    name = models.CharField(max_length=255)

    nginx_config_template = models.ForeignKey(
        "NginxConfigTemplate", on_delete=models.SET_NULL, related_name="nodes", null=True, blank=True
    )

    def clean(self):
        super().clean()
        if self.nginx_config_template and self.nginx_config_template.type != ConfigTemplate.TypeChoices.NGINX:
            raise ValidationError


class NodeAPIKey(TimeStampedModel, AbstractAPIKey):
    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="apikeys",
    )


class ConfigTemplate(TimeStampedModel, models.Model):
    name = models.CharField(max_length=255)
    template = models.TextField()


class NginxConfigTemplate(ConfigTemplate):
    pass


class EasyTierProtocolChoices(models.TextChoices):
    TCP = "tcp"
    UDP = "udp"
    WS = "ws"
    WSS = "wss"


class EasyTierNodePeer(TimeStampedModel):
    peer = models.ForeignKey("EasyTierNode", on_delete=models.CASCADE, related_name="peer_nodepeers")
    node = models.ForeignKey("EasyTierNode", on_delete=models.CASCADE, related_name="node_nodepeer")
    protocol = models.CharField(max_length=15, choices=EasyTierProtocolChoices.choices)

    def clean(self):
        super().clean()
        if self.protocol not in (available_protocols := self.peer.exposed_protocols()):
            raise ValidationError(f"{self.protocol} not available in {self.peer}, {available_protocols} are available")


class EasyTierListener(TimeStampedModel):
    protocol = models.CharField(max_length=15, choices=EasyTierProtocolChoices.choices)
    port = models.PositiveSmallIntegerField()


class EasyTierNode(TimeStampedModel):
    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="easytiers",
    )
    peers = models.ManyToManyField("Self", related_name="peers_easytiers")
    external_node = models.CharField(max_length=255, help_text="tcp://public.easytier.top:11010")
    network_name = models.CharField(max_length=255)
    network_secret = models.CharField(max_length=255)
    listeners = models.ManyToManyField(EasyTierListener, related_name="easytiernodes")

    def exposed_protocols(self):
        res = set()
        if listener_qs := self.listeners.all():
            res = set(listener_qs.values_list("protocol", flat=True))
        return res

    def clean(self):
        super().clean()
