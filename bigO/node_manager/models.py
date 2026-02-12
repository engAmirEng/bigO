from __future__ import annotations

import logging
import random
import urllib.parse
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Self, TypedDict

import netfields
from rest_framework_api_key.models import AbstractAPIKey
from simple_history.models import HistoricalRecords
from solo.models import SingletonModel
from taggit.managers import TaggableManager

import django.template.loader
from bigO.core import models as core_models
from bigO.utils.models import MakeInterval, TimeStampedModel, async_related_obj_str
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Case, ExpressionWrapper, F, OuterRef, Q, Subquery, Sum, UniqueConstraint, When
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


class Config(SingletonModel):
    admin_show_node_metrics = models.BooleanField(default=False)


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


class NetplanConfiguration(TimeStampedModel, models.Model):
    name = models.SlugField(unique=True)
    template = models.ForeignKey("Snippet", on_delete=models.PROTECT, related_name="+")
    dnsv4 = models.CharField(max_length=255)
    dnsv6 = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.id}-{self.name}"


class O2Spec(TimeStampedModel, models.Model):
    node = models.OneToOneField("Node", on_delete=models.CASCADE, related_name="o2spec")
    program = models.ForeignKey("ProgramVersion", on_delete=models.PROTECT, related_name="program_o2spec")
    sync_domain = models.URLField(max_length=255)
    api_key = models.CharField(max_length=255)
    interval_sec = models.PositiveSmallIntegerField()
    working_dir = models.CharField(max_length=255)
    sentry_dsn = models.URLField(max_length=255, null=True, blank=True)
    full_control_supervisord = models.BooleanField(default=False)
    keep_latest_config = models.BooleanField(default=True)

    @property
    def sync_url(self):
        return urllib.parse.urljoin(self.sync_domain, reverse("node_manager:node_base_sync_v2"))


class SystemArchitectureTextChoices(models.TextChoices):
    AMD64 = "amd64"


class GenericStatusChoices(models.IntegerChoices):
    NEVER = 4, "never"
    ONLINE = 5, "online"
    ERROR = 1, "error"
    OFFLINE = 2, "offline"
    ATTENDED_OFFLINE = 3, "attended offline"


class Node(TimeStampedModel, models.Model):
    is_revoked = models.BooleanField(default=False)
    downtime_attended = models.BooleanField(default=False)
    name = models.SlugField(max_length=255, unique=True)
    is_tunable = models.BooleanField(default=True, help_text="can tuns be created on it?")
    container_spec = models.OneToOneField(
        ContainerSpec, related_name="containerspec_nodes", on_delete=models.PROTECT, null=True, blank=True
    )
    netplan_config = models.ForeignKey(
        NetplanConfiguration, on_delete=models.PROTECT, related_name="+", null=True, blank=True
    )
    architecture = models.CharField(max_length=63, choices=SystemArchitectureTextChoices.choices)
    default_cert = models.ForeignKey("core.Certificate", on_delete=models.SET_NULL, null=True, blank=True)
    collect_metrics = models.BooleanField(default=False)
    collect_logs = models.BooleanField(default=False)
    tmp_xray = models.BooleanField(default=False)
    ssh_port = models.PositiveSmallIntegerField(null=True, blank=True)
    ssh_user = models.CharField(max_length=255, null=True, blank=True)
    ssh_pass = models.CharField(max_length=255, null=True, blank=True)
    ssh_public_keys = models.ManyToManyField("core.PublicKey", related_name="+", blank=True)
    ansible_deploy_snippet = models.ForeignKey(
        "Snippet", on_delete=models.PROTECT, related_name="ansibledeploysnippet_nodes", null=True, blank=True
    )

    class NodeQuerySet(models.QuerySet):
        def support_ipv6(self):
            return self.filter(node_nodepublicips__ip__ip__family=6)

        def ann_is_online(self, defualt_interval_sec=20):
            now = timezone.now()
            defualt_interval_coefficient = 2
            return self.annotate(
                expected_sync_delay=MakeInterval(
                    ExpressionWrapper(
                        Coalesce(F("node_nodesyncstat__expected_interval_coefficient"), defualt_interval_coefficient)
                        * Coalesce(F("o2spec__interval_sec"), defualt_interval_sec),
                        output_field=models.DurationField(),
                    )
                ),
                is_online=Case(
                    When(
                        Q(node_nodesyncstat__initiated_at__isnull=False),
                        then=ExpressionWrapper(
                            Q(node_nodesyncstat__initiated_at__gt=now - F("expected_sync_delay")),
                            output_field=models.BooleanField(),
                        ),
                    ),
                    default=False,
                ),
            )

        def ann_generic_status(self, default_acceptable_response_time=timedelta(milliseconds=1_200)):
            # call ann_is_online first
            now = timezone.now()
            return self.annotate(
                generic_status=Case(
                    When(
                        Q(is_online=True, node_nodesyncstat__initiated_at__isnull=True),
                        then=GenericStatusChoices.ONLINE,
                    ),
                    When(
                        Q(is_online=True, node_nodesyncstat__initiated_at__isnull=False)
                        & Q(
                            Q(node_nodesyncstat__respond_at__isnull=True)
                            | Q(node_nodesyncstat__respond_at__lt=F("node_nodesyncstat__initiated_at"))
                        )
                        & Q(node_nodesyncstat__initiated_at__lt=now - default_acceptable_response_time),
                        then=GenericStatusChoices.ERROR,
                    ),
                    When(is_online=True, then=GenericStatusChoices.ONLINE),
                    When(
                        Q(is_online=False)
                        & Q(Q(node_nodesyncstat__isnull=True) | Q(node_nodesyncstat__initiated_at__isnull=True)),
                        then=GenericStatusChoices.NEVER,
                    ),
                    When(Q(is_online=False, downtime_attended=True), then=GenericStatusChoices.ATTENDED_OFFLINE),
                    When(Q(is_online=False), then=GenericStatusChoices.OFFLINE),
                )
            )

    objects = NodeQuerySet.as_manager()

    def __str__(self):
        first_ip = self.node_nodepublicips.first()
        prefix = ""
        if first_ip:
            prefix = first_ip.ip.get_region_display()
        return f"{'❌' if self.is_revoked else ''}{self.pk}-{prefix}{self.name}"

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

    def get_asn_domain(self) -> core_models.Domain:
        """used in templates, deprecated, use get_reality"""
        from bigO.proxy_manager.models import RealitySpec

        realityspec = RealitySpec.objects.filter(
            inbound_type__isnull=True, for_ip__ip_nodepublicips__node=self, port=443
        ).first()
        if realityspec:
            return realityspec.certificate_domain

    def get_reality(self, port=443) -> dict:
        """used in templates"""
        from bigO.proxy_manager.models import RealitySpec

        realityspec = RealitySpec.objects.filter(
            inbound_type__isnull=True, for_ip__ip_nodepublicips__node=self, port=port
        ).first()
        if realityspec:
            if realityspec.dest_ip:
                dest = str(realityspec.dest_ip.ip.ip)
            else:
                dest = realityspec.certificate_domain.name
            return {"dest": dest + ":" + str(realityspec.port), "domain": realityspec.certificate_domain.name}


class AnsibleTask(TimeStampedModel, models.Model):
    class AnsibleTaskQuerySet(models.QuerySet):
        def ann_stats(self):
            return self.annotate(
                ok=Sum("task_nodes__ok"),
                dark=Sum("task_nodes__dark"),
                changed=Sum("task_nodes__changed"),
                failures=Sum("task_nodes__failures"),
            )

    class StatusChoices(models.IntegerChoices):
        STARTED = 1, "started"
        FINISHED = 2, "finished"

    name = models.CharField(max_length=255)
    celery_task_id = models.UUIDField(null=True, blank=True)
    playbook_snippet = models.ForeignKey(
        "Snippet", on_delete=models.SET_NULL, related_name="playbooksnippet_ansibletasks", null=True, blank=True
    )
    playbook_content = models.TextField()
    inventory_content = models.TextField(null=True, blank=True)
    extravars = models.JSONField(null=True, blank=True)
    status = models.PositiveSmallIntegerField(choices=StatusChoices)
    logs = models.TextField(blank=True)
    result = models.JSONField(null=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    objects = AnsibleTaskQuerySet.as_manager()

    def __str__(self):
        return f"{self.pk}-{self.name}"

    @property
    def ok(self) -> int:
        return self._ok

    @ok.setter
    def ok(self, value):
        self._ok = value

    @property
    def dark(self) -> int:
        return self._dark

    @dark.setter
    def dark(self, value):
        self._dark = value

    @property
    def changed(self) -> int:
        return self._changed

    @changed.setter
    def changed(self, value):
        self._changed = value

    @property
    def failures(self) -> int:
        return self._failures

    @failures.setter
    def failures(self, value):
        self._failures = value


class AnsibleTaskNode(TimeStampedModel, models.Model):
    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="node_ansibletasks")
    task = models.ForeignKey(AnsibleTask, on_delete=models.CASCADE, related_name="task_nodes")
    ok = models.PositiveSmallIntegerField(null=True, blank=True)
    dark = models.PositiveSmallIntegerField(null=True, blank=True)
    changed = models.PositiveSmallIntegerField(null=True, blank=True)
    failures = models.PositiveSmallIntegerField(null=True, blank=True)
    result = models.JSONField(null=True)


class NodeSupervisorConfig(TimeStampedModel, models.Model):
    node = models.OneToOneField(Node, on_delete=models.CASCADE, related_name="supervisorconfig")
    xml_rpc_api_expose_port = models.IntegerField(null=True, blank=True)


class NodeAPIKey(TimeStampedModel, AbstractAPIKey):
    node = models.ForeignKey(
        Node,
        on_delete=models.CASCADE,
        related_name="apikeys",
    )


class PublicIPQuerySet(models.QuerySet):
    def ann_node(self):
        nodepublicip_qs = NodePublicIP.objects.filter(ip_id=OuterRef("id"))
        return self.annotate(
            node_name=Subquery(nodepublicip_qs.values("node__name")),
            node_id=Subquery(nodepublicip_qs.values("node__id")),
        )


class PublicIP(TimeStampedModel):
    class PublicIPManager(models.Manager):
        def get_queryset(self):
            return PublicIPQuerySet(model=self.model, using=self._db, hints=self._hints).ann_node()

    name = models.CharField(max_length=255, null=True, blank=True)
    ip = netfields.InetAddressField(unique=True)
    is_cdn = models.BooleanField(default=False)
    isp = models.ForeignKey(
        "proxy_manager.ISP", on_delete=models.PROTECT, related_name="isp_publicips", null=True, blank=True
    )
    region = models.ForeignKey(
        "proxy_manager.Region", on_delete=models.PROTECT, related_name="region_publicips", null=True, blank=True
    )
    asn = models.PositiveIntegerField(null=True, blank=True)

    objects = PublicIPManager()

    def __str__(self):
        prefix = self.get_region_display()
        try:
            if self.node_name:
                return f"{self.pk}-{prefix}{self.ip.ip} -> {self.node_id}-{self.node_name}"
        except AttributeError:
            pass
        return f"{self.pk}-{prefix}{self.ip.ip}"

    def get_region_display(self):
        prefix = ""
        if self.region and self.region.short_display:
            prefix = self.region.short_display
        return prefix

    @property
    def node_name(self):
        return self._node_name

    @node_name.setter
    def node_name(self, value):
        self._node_name = value

    @property
    def node_id(self):
        return self._node_id

    @node_id.setter
    def node_id(self, value):
        self._node_id = value


class NodePublicIP(TimeStampedModel):
    class StatusChoices(models.IntegerChoices):
        UNKNOWN = 1, "unknown"
        OK = 2, "ok"
        PROBLEM = 3, "problem"

    node = models.ForeignKey(Node, on_delete=models.CASCADE, related_name="node_nodepublicips")
    ip = models.ForeignKey(PublicIP, on_delete=models.CASCADE, related_name="ip_nodepublicips")
    status = models.PositiveSmallIntegerField(choices=StatusChoices.choices, default=StatusChoices.UNKNOWN)
    last_status_check = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [UniqueConstraint(fields=("ip", "node"), name="unique_node_ip")]

    def __str__(self):
        perfix = self.ip.get_region_display()
        return f"{self.pk}-{self.node.name}|{self.mark}{perfix}{self.ip.ip}"

    @property
    def mark(self):
        return (
            "❕"
            if self.status == NodePublicIP.StatusChoices.UNKNOWN
            else "⚠️"
            if self.status == NodePublicIP.StatusChoices.PROBLEM
            else ""
        )


class Snippet(TimeStampedModel, models.Model):
    name = models.SlugField()
    template = models.TextField()

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.pk}-{self.name}"


class Program(TimeStampedModel):
    name = models.CharField(max_length=127, unique=True)

    def __str__(self):
        return f"{self.pk}-{self.name}"


class ProgramVersion(TimeStampedModel):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="program_programversion")
    version = models.CharField(max_length=63)

    class Meta:
        ordering = ["-created_at"]
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
        program_str = async_related_obj_str(self, ProgramVersion.program)
        return f"{self.pk}-{program_str} ({self.version})"


class SupervisorProcessInfo(TimeStampedModel, models.Model):
    class ProcessState(models.IntegerChoices):
        STOPPED = 0, "stopped"
        STARTING = 10, "starting"
        RUNNING = 20, "running"
        BACKOFF = 30, "backoff"
        STOPPING = 40, "stopping"
        EXITED = 100, "exited"
        FATAL = 200, "fatal"
        UNKNOWN = 1000, "unknown"

    node = models.ForeignKey("Node", on_delete=models.CASCADE, related_name="node_processstates")
    is_down_attended = models.BooleanField(default=False)
    name = models.CharField(max_length=255)
    group: models.CharField(max_length=255)
    description = models.CharField(max_length=255)
    perv_state = models.PositiveSmallIntegerField(choices=ProcessState.choices)
    last_state = models.PositiveSmallIntegerField(choices=ProcessState.choices)
    perv_statename = models.CharField(max_length=255)
    last_statename = models.CharField(max_length=255)
    perv_start = models.DateTimeField()
    last_start = models.DateTimeField()
    perv_stop = models.DateTimeField(null=True, blank=True)
    last_stop = models.DateTimeField(null=True, blank=True)
    perv_spawnerr = models.CharField(max_length=255, null=True, blank=True)
    last_spawnerr = models.CharField(max_length=255, null=True, blank=True)
    perv_exitstatus = models.SmallIntegerField(null=True, blank=True)
    last_exitstatus = models.SmallIntegerField(null=True, blank=True)
    perv_pid = models.PositiveBigIntegerField(null=True, blank=True)
    last_pid = models.PositiveBigIntegerField(null=True, blank=True)
    stdout_logfile = models.CharField(max_length=255)
    stderr_logfile = models.CharField(max_length=255)
    perv_captured_at = models.DateTimeField()
    last_captured_at = models.DateTimeField()
    perv_changed_at = models.DateTimeField()
    last_changed_at = models.DateTimeField()

    class Meta:
        ordering = ["-last_captured_at"]
        constraints = [UniqueConstraint(fields=("node", "name"), name="unique_name_node_for_supervisor")]

    def __str__(self):
        return f"{self.name}|{self.node}"


class CustomConfig(TimeStampedModel, models.Model):
    name = models.CharField(max_length=255)
    program_version = models.ForeignKey(
        ProgramVersion,
        on_delete=models.PROTECT,
        related_name="programversion_customconfigs",
        null=True,
        blank=True,
        help_text="depracated",
    )
    run_opts_template = models.TextField(help_text="{node_obj}, *#path:key#*")
    tags = TaggableManager(related_name="tag_customconfigs", blank=True)

    history = HistoricalRecords()

    def __str__(self):
        return f"{self.pk}-{self.name}"


class CustomConfigDependantFile(TimeStampedModel, models.Model):
    customconfig = models.ForeignKey(CustomConfig, on_delete=models.CASCADE, related_name="dependantfiles")
    key = models.SlugField()
    template = models.TextField(null=True, blank=True, help_text="{node_obj}")
    file = models.ForeignKey(
        ProgramVersion, on_delete=models.PROTECT, related_name="customconfigdependants", null=True, blank=True
    )
    name_extension = models.CharField(max_length=15, null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            UniqueConstraint(fields=("customconfig", "key"), name="unique_slug_customconfig"),
        ]

    def clean(self):
        if self.template and self.file:
            return ValidationError("file or template not both")

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
        ordering = ["-created_at"]
        constraints = [UniqueConstraint(fields=("node", "custom_config"), name="unique_node_custom_config")]

    def get_program(self) -> NodeInnerProgram | ProgramBinary | None:
        res = self.node.node_nodeinnerbinary.filter(program_version=self.custom_config.program_version).first()
        if res is None:
            res = ProgramBinary.objects.filter(
                program_version=self.custom_config.program_version, architecture=self.node.architecture
            ).first()
        return res

    def get_config_dependent_content(self) -> list[ConfigDepandantContent]:
        context = {"node_obj": self.node}
        res = []
        for i in self.custom_config.dependantfiles.all():
            template = django.template.Template("{% load node_manager %}" + i.template)
            result = template.render(context=django.template.Context(context))
            res.append({"key": i.key, "content": result, "extension": i.name_extension})

        return res

    def get_run_opts(self) -> str:
        context = {"node_obj": self.node, "configfile_path_placeholder": "CONFIGFILEPATH"}
        template = django.template.Template("{% load node_manager %}" + self.custom_config.run_opts_template)
        result = template.render(context=django.template.Context(context))
        return result

    def get_hash(self) -> str:
        influential = ""
        influential += self.get_run_opts()
        if config_depandant_content := self.get_config_dependent_content():
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
        return program_version.get_program_for_node(self.node)

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
        max_first_touch_to_nodes = 5
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

        all_available_node_peers = []
        peers = []
        kept_current_nodepeers = []
        new_nodepeers = []
        current_nodepeers_qs = self.node_nodepeers.all()
        for network_easytiernode in self.network.network_easytiernodes.filter(node__is_revoked=False).exclude(
            id=self.id
        ):
            nodepublicips_qs = network_easytiernode.node.node_nodepublicips.all()
            if not self.node.get_support_ipv6():
                nodepublicips_qs = nodepublicips_qs.exclude(ip__ip__family=6)
            for nodepublicip in nodepublicips_qs:
                for nodelistener in network_easytiernode.node_nodelisteners.all():
                    peer = EasyTierNodePeer()
                    peer.node = self
                    peer.peer_listener = nodelistener
                    peer.peer_public_ip = nodepublicip
                    all_available_node_peers.append(peer)

            for i in all_available_node_peers:
                for j in current_nodepeers_qs:
                    if not j.does_need_recreation_to(i):
                        kept_current_nodepeers.append(j)
                        break
                else:
                    new_nodepeers.append(i)
        current_nodepeers_qs.exclude(id__in=[i.id for i in kept_current_nodepeers]).delete()
        keeping_nodepeers = current_nodepeers_qs.filter(id__in=[i.id for i in kept_current_nodepeers])
        first_touch_to_nodes = len(keeping_nodepeers)
        random.shuffle(new_nodepeers)
        for i in new_nodepeers:
            if first_touch_to_nodes >= max_first_touch_to_nodes:
                break
            i.save()
            first_touch_to_nodes += 1
        for nodepeer in self.node_nodepeers.all():
            if nodepeer.peer_public_ip.ip.ip.ip.version == 6:
                ip_part = f"[{nodepeer.peer_public_ip.ip.ip.ip}]"
            else:
                ip_part = str(nodepeer.peer_public_ip.ip.ip.ip)
            peer = f"{nodepeer.peer_listener.protocol}://{ip_part}:{nodepeer.peer_listener.port}"
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
        ordering = ["-created_at"]
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


class ProgramBinary(TimeStampedModel):
    program_version = models.ForeignKey(
        ProgramVersion, on_delete=models.CASCADE, related_name="programversion_programbinaries"
    )
    architecture = models.CharField(max_length=63, choices=SystemArchitectureTextChoices.choices)
    file = models.FileField(upload_to="protected/")
    hash = models.CharField(max_length=64, blank=False, db_index=True)

    class Meta:
        ordering = ["-created_at"]
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
        ordering = ["-created_at"]
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
    expected_interval_coefficient = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal(1.5))
    mean_interval_up_to_now = models.PositiveBigIntegerField(null=True, blank=True)
    count_up_to_now = models.BigIntegerField()
    agent_spec = models.CharField(max_length=255, null=True, blank=True)
    initiated_at = models.DateTimeField(null=True, blank=True)
    config = models.JSONField(null=True, blank=True)
    respond_at = models.DateTimeField(null=True, blank=True)
    request_headers = models.JSONField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    ip_a = models.TextField(null=True, blank=True)
