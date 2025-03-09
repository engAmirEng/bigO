from __future__ import annotations

import logging
from hashlib import sha256
from typing import Self, TypedDict

import netfields
from rest_framework_api_key.models import AbstractAPIKey
from solo.models import SingletonModel
from taggit.managers import TaggableManager

import django.template.loader
from bigO.core import models as core_models
from bigO.utils.models import TimeStampedModel
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, UniqueConstraint

logger = logging.getLogger(__name__)


class ContainerSpec(TimeStampedModel):
    ipv4 = netfields.InetAddressField(
        validators=[validators.validate_ipv4_address],
        null=True,
        blank=True,
        help_text="the internal ip that is constantly changed, this is a stational entity",
    )  # stational entity
    ip_a_container_ipv4_extractor = models.ForeignKey(
        "utils.TextExtractor",
        related_name="ipacontaineripv4extractor_containerspecs",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    ipv6 = netfields.InetAddressField(
        validators=[validators.validate_ipv6_address],
        null=True,
        blank=True,
        help_text="the internal ip that is constantly changed, this is a stational entity",
    )  # stational entity
    ip_a_container_ipv6_extractor = models.ForeignKey(
        "utils.TextExtractor",
        related_name="ipacontaineripv6extractor_containerspecs",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )


class SystemArchitectureTextChoices(models.TextChoices):
    AMD64 = "amd64"


class Node(TimeStampedModel, models.Model):
    name = models.SlugField(max_length=255, unique=True)
    is_tunable = models.BooleanField(default=True, help_text="can tuns be created on it?")
    container_spec = models.OneToOneField(
        ContainerSpec, related_name="containerspec_nodes", on_delete=models.PROTECT, null=True, blank=True
    )
    architecture = models.CharField(max_length=63, choices=SystemArchitectureTextChoices.choices)
    default_cert = models.ForeignKey("core.Certificate", on_delete=models.SET_NULL, null=True, blank=True)
    collect_metrics = models.BooleanField(default=False)
    collect_logs = models.BooleanField(default=False)

    class NodeQuerySet(models.QuerySet):
        def support_ipv6(self):
            return self.filter(node_nodepublicips__ip__ip__family=6)

    objects = NodeQuerySet.as_manager()

    def __str__(self):
        return f"{self.pk}-{self.name}"

    def get_support_ipv6(self):
        return Node.objects.filter(id=self.id).support_ipv6().exists()

    def get_default_cert(self):
        from . import services

        if self.default_cert:
            return self.default_cert
        cert = services.create_default_cert_for_node(self)
        self.default_cert = cert
        self.save()
        return self.default_cert


class NodeSupervisorConfig(TimeStampedModel, models.Model):
    node = models.OneToOneField(Node, on_delete=models.CASCADE, related_name="supervisorconfig")
    xml_rpc_api_expose_port = models.IntegerField(null=True, blank=True)


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
    isp = models.ForeignKey(
        "proxy_manager.ISP", on_delete=models.PROTECT, related_name="isp_publicips", null=True, blank=True
    )
    region = models.ForeignKey(
        "proxy_manager.Region", on_delete=models.PROTECT, related_name="region_publicips", null=True, blank=True
    )

    def __str__(self):
        return f"{self.pk}-{self.ip.ip}"


class NodePublicIP(TimeStampedModel):
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="node_nodepublicips")
    ip = models.ForeignKey(PublicIP, on_delete=models.CASCADE, related_name="ip_nodepublicips")

    class Meta:
        constraints = [UniqueConstraint(fields=("ip", "node"), name="unique_node_ip")]

    def __str__(self):
        return f"{self.pk}-{self.node}|{self.ip}"


class Program(TimeStampedModel):
    name = models.CharField(max_length=127, unique=True)

    def __str__(self):
        return f"{self.pk}-{self.name}"


class ProgramVersion(TimeStampedModel):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="program_programversion")
    version = models.CharField(max_length=63)

    class Meta:
        constraints = [UniqueConstraint(fields=("program", "version"), name="unique_program_version")]

    def get_program_for_node(self, node: Node) -> NodeInnerProgram | ProgramBinary | None:
        """
        returns the appropriate program with priority of NodeInnerProgram and then ProgramBinary
        """
        res = node.node_nodeinnerbinary.filter(program_version=self).first()
        if res is None:
            res = ProgramBinary.objects.filter(program_version=self, architecture=node.architecture).first()
        return res

    def __str__(self):
        return f"{self.pk}-{self.program} ({self.version})"


class CustomConfig(TimeStampedModel, models.Model):
    name = models.CharField(max_length=255)
    program_version = models.ForeignKey(
        ProgramVersion,
        on_delete=models.PROTECT,
        related_name="programversion_customconfigs",
    )
    run_opts_template = models.TextField(help_text="{node_obj, configfile_path_placeholder}")
    tags = TaggableManager(related_name="tag_customconfigs", blank=True)

    def __str__(self):
        return f"{self.pk}-{self.name}"


class CustomConfigDependantFile(TimeStampedModel, models.Model):
    customconfig = models.ForeignKey(CustomConfig, on_delete=models.CASCADE, related_name="dependantfiles")
    key = models.SlugField()
    template = models.TextField(help_text="{node_obj}")
    template_extension = models.CharField(max_length=15, null=True, blank=True)

    class Meta:
        constraints = [UniqueConstraint(fields=("customconfig", "key"), name="unique_slug_customconfig")]

    def __str__(self):
        return f"{self.pk}-{self.key}: for config {str(self.customconfig)}"


class ConfigDepandantContent(TypedDict):
    key: str
    content: str
    extension: str | None


class NodeCustomConfig(TimeStampedModel):
    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="node_customconfigs",
    )
    custom_config = models.ForeignKey(CustomConfig, on_delete=models.CASCADE, related_name="nodecustomconfigs")
    stdout_action_type = models.PositiveSmallIntegerField(
        choices=core_models.LogActionType.choices, default=core_models.LogActionType.NOTHING
    )
    stderr_action_type = models.PositiveSmallIntegerField(
        choices=core_models.LogActionType.choices, default=core_models.LogActionType.NOTHING
    )

    class Meta:
        constraints = [UniqueConstraint(fields=("node", "custom_config"), name="unique_node_custom_config")]

    def get_program(self) -> NodeInnerProgram | ProgramBinary | None:
        res = self.node.node_nodeinnerbinary.filter(program_version=self.custom_config.program_version).first()
        if res is None:
            res = ProgramBinary.objects.filter(
                program_version=self.custom_config.program_version, architecture=self.node.architecture
            ).first()
        return res

    def get_config_depandant_content(self) -> list[ConfigDepandantContent]:
        context = {"node_obj": self.node}
        res = []
        for i in self.custom_config.dependantfiles.all():
            template = django.template.Template("{% load node_manager %}" + i.template)
            result = template.render(context=django.template.Context(context))
            res.append({"key": i.key, "content": result, "extension": i.template_extension})

        return res

    def get_run_opts(self) -> str:
        context = {"node_obj": self.node, "configfile_path_placeholder": "CONFIGFILEPATH"}
        template = django.template.Template("{% load node_manager %}" + self.custom_config.run_opts_template)
        result = template.render(context=django.template.Context(context))
        return result

    def get_hash(self) -> str:
        influential = ""
        influential += self.get_run_opts()
        if config_depandant_content := self.get_config_depandant_content():
            for i in config_depandant_content:
                influential += i["content"]
        program = self.get_program()
        if isinstance(program, ProgramBinary):
            influential += program.hash
        elif isinstance(program, NodeInnerProgram):
            influential += program.path
        return sha256(influential.encode("utf-8")).hexdigest()

    def __str__(self):
        return f"{self.pk}-{self.node}|{self.custom_config}"


class EasyTierNetwork(TimeStampedModel):
    network_name = models.CharField(max_length=255, unique=True)
    network_secret = models.CharField(max_length=255)
    ip_range = netfields.CidrAddressField()
    program_version = models.ForeignKey(
        ProgramVersion, on_delete=models.PROTECT, related_name="programversion_easytiernetworks"
    )

    def __str__(self):
        return f"{self.pk}-{self.network_name}"

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
    preferred_program_version = models.ForeignKey(
        ProgramVersion,
        on_delete=models.PROTECT,
        related_name="preferredprogramversion_easytiernode",
        null=True,
        blank=True,
    )
    ipv4 = netfields.InetAddressField(
        null=True, blank=True, help_text="this is a stational entity"
    )  # stational entity
    mtu = models.PositiveSmallIntegerField(null=True, blank=True)
    latency_first = models.BooleanField(default=False)
    rpc_portal_port = models.PositiveSmallIntegerField(null=True, blank=True)
    custom_toml_config_template = models.TextField(null=True, blank=True)
    custom_run_opts_template = models.TextField(null=True, blank=True)
    stdout_action_type = models.PositiveSmallIntegerField(
        choices=core_models.LogActionType.choices, default=core_models.LogActionType.NOTHING
    )
    stderr_action_type = models.PositiveSmallIntegerField(
        choices=core_models.LogActionType.choices, default=core_models.LogActionType.NOTHING
    )

    class EasyTierNodeQuerySet(models.QuerySet):
        def ann_can_create_tun(self):
            return self.annotate(can_create_tun=F("node__is_tunable"))

        def can_create_tun(self):
            return self.ann_can_create_tun().filter(can_create_tun=True)

    objects = EasyTierNodeQuerySet.as_manager()

    def __str__(self):
        return f"{self.pk}-{self.node}|{self.network}"

    def get_program(self) -> NodeInnerProgram | ProgramBinary | None:
        """
        returns the appropriate program with priority of NodeInnerProgram and then ProgramBinary
        """
        program_version = self.preferred_program_version or self.network.program_version
        res = self.node.node_nodeinnerbinary.filter(program_version=program_version).first()
        if res is None:
            res = ProgramBinary.objects.filter(
                program_version=program_version, architecture=self.node.architecture
            ).first()
        return res

    def get_hash(self) -> str:
        influential = ""
        influential += self.get_run_opts()
        if config_content := self.get_toml_config_content():
            influential += config_content
        program = self.get_program()
        if isinstance(program, ProgramBinary):
            influential += program.hash
        elif isinstance(program, NodeInnerProgram):
            influential += program.path
        return sha256(influential.encode("utf-8")).hexdigest()

    def get_can_create_tun(self):
        return EasyTierNode.objects.filter(id=self.id).can_create_tun().exists()

    def get_run_opts(self):
        context = {"easytier_node_obj": self, "configfile_path_placeholder": "CONFIGFILEPATH"}
        if self.custom_run_opts_template:
            template = django.template.Template("{% load node_manager %}" + self.custom_run_opts_template)
            result = template.render(context=django.template.Context(context))
        else:
            template = django.template.loader.get_template("node_manager/configs/easytier_opts.txt")
            result = template.render(context)
        return result

    @transaction.atomic(using="main")
    def get_toml_config_content(self):
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
        for network_easytiernode in self.network.network_easytiernodes.exclude(id=self.id):
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
            peer = (
                f"{nodepeer.peer_listener.protocol}://{nodepeer.peer_public_ip.ip.ip.ip}:{nodepeer.peer_listener.port}"
            )
            peers.append(peer)

        proxy_networks = []
        if self.node.container_spec and self.node.container_spec.ipv4:
            proxy_networks.append(str(self.node.container_spec.ipv4))

        context = {
            "easytier_node_obj": self,
            "ipv4": ipv4,
            "mtu": self.mtu,
            "external_node": self.external_node,
            "peers": peers,
            "proxy_networks": proxy_networks,
        }
        if self.custom_toml_config_template:
            template = django.template.Template("{% load node_manager %}" + self.custom_toml_config_template)
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

    def __str__(self):
        return f"{self.pk}-{self.node}({self.protocol}:{self.port})"


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


class XrayConfig(TimeStampedModel, SingletonModel):
    program_version = models.ForeignKey(
        ProgramVersion, on_delete=models.PROTECT, related_name="programversion_xrayconfig"
    )
    content = models.TextField()


class GostClientNode(TimeStampedModel):
    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="gostservers",
    )


class ProgramBinary(TimeStampedModel):
    program_version = models.ForeignKey(
        ProgramVersion, on_delete=models.CASCADE, related_name="programversion_programbinaries"
    )
    architecture = models.CharField(max_length=63, choices=SystemArchitectureTextChoices.choices)
    file = models.FileField(upload_to="protected/")
    hash = models.CharField(max_length=64, blank=False, db_index=True)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=("architecture", "program_version"),
                name="unique_architecture_programversion",
            ),
        ]

    def __str__(self):
        return f"{self.pk}-{self.program_version}({self.architecture})"

    def set_hash(self):
        binary_data = self.file.read()
        self.hash = self.get_hash(binary_data)

    @staticmethod
    def get_hash(file: bytes):
        return sha256(file).hexdigest()


class NodeInnerProgram(TimeStampedModel):
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="node_nodeinnerbinary")
    path = models.CharField(max_length=255, null=True, blank=True)
    program_version = models.ForeignKey(
        ProgramVersion, on_delete=models.CASCADE, related_name="programversion_nodeinnerprograms"
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=("path", "node"),
                name="node_path_taken",
                violation_error_message="this path is already taken on the node.",
            ),
            UniqueConstraint(
                fields=("program_version", "node"),
                name="innerprogram_unique_programversion_node",
                violation_error_message="this kind of program is already defined for this node node.",
            ),
        ]

    def __str__(self):
        return f"{self.pk}-{self.node}|{self.program_version}"


class NodeLatestSyncStat(TimeStampedModel, models.Model):
    node = models.OneToOneField(Node, on_delete=models.CASCADE, related_name="node_nodesyncstat")
    agent_spec = models.CharField(max_length=255, null=True, blank=True)
    initiated_at = models.DateTimeField()
    respond_at = models.DateTimeField(null=True)
    request_headers = models.JSONField()
    response_payload = models.JSONField(null=True)
    count_up_to_now = models.BigIntegerField()
