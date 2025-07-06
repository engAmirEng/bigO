from zoneinfo import ZoneInfo

from solo.models import SingletonModel

from bigO.utils.models import TimeStampedModel
from django.core import validators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, OuterRef, Q, Subquery, UniqueConstraint
from django.utils import timezone
from django.utils.translation import gettext

from .dns import AVAILABLE_DNS_PROVIDERS
from .dns.base import BaseDNSProvider


class LogActionType(models.IntegerChoices):
    NOTHING = 0, "nothing"
    TO_LOKI = 1, "to loki"


class SiteConfiguration(SingletonModel):
    sync_brake = models.BooleanField(default=True)
    nodes_ca_cert = models.ForeignKey("Certificate", on_delete=models.PROTECT, null=True, blank=False)
    main_nginx = models.ForeignKey(
        "node_manager.ProgramVersion", on_delete=models.PROTECT, related_name="+", null=True, blank=False
    )
    main_goingto = models.ForeignKey(
        "node_manager.ProgramVersion", on_delete=models.PROTECT, related_name="+", null=True, blank=False
    )
    main_telegraf = models.ForeignKey(
        "node_manager.ProgramVersion", on_delete=models.PROTECT, related_name="+", null=True, blank=False
    )
    main_nginx_stdout_action_type = models.PositiveSmallIntegerField(
        choices=LogActionType.choices, default=LogActionType.NOTHING
    )
    main_nginx_stderr_action_type = models.PositiveSmallIntegerField(
        choices=LogActionType.choices, default=LogActionType.NOTHING
    )
    main_haproxy = models.ForeignKey(
        "node_manager.ProgramVersion", on_delete=models.PROTECT, related_name="+", null=True, blank=False
    )
    main_xray = models.ForeignKey(
        "node_manager.ProgramVersion", on_delete=models.PROTECT, related_name="+", null=True, blank=False
    )
    loki_batch_size = models.PositiveBigIntegerField(default=1 * 1024 * 1024)
    basic_username = models.CharField(max_length=255, blank=False, null=True)
    basic_password = models.CharField(max_length=255, blank=False, null=True)
    htpasswd_content = models.TextField(blank=True, null=True)

    def clean(self):
        if self.nodes_ca_cert:
            if not self.nodes_ca_cert.private_key:
                raise ValidationError("nodes_ca_cert should have private_key")
            error_msg = self.nodes_ca_cert.is_chain_complete()
            if error_msg:
                raise ValidationError(error_msg)


class AbstractCryptographicObject(models.Model):
    class AlgorithmChoices(models.IntegerChoices):
        RSA = 1, "RSA"
        ECDSA = 2, "ECDSA"

    slug = models.CharField(unique=True, max_length=255)
    algorithm = models.PositiveSmallIntegerField(AlgorithmChoices.choices)
    content = models.TextField()

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.pk}-{self.slug}"


class PrivateKey(AbstractCryptographicObject, TimeStampedModel, models.Model):
    passphrase = models.CharField(max_length=255, null=True, blank=True)
    key_length = models.PositiveSmallIntegerField()


class Certificate(AbstractCryptographicObject, TimeStampedModel, models.Model):
    is_ca = models.BooleanField(default=False)
    fingerprint = models.CharField(max_length=64, blank=False, db_index=True)
    private_key = models.ForeignKey(PrivateKey, on_delete=models.CASCADE, null=True, blank=True)
    parent_certificate = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    certbot_info = models.ForeignKey(
        "CertbotInfo", on_delete=models.SET_NULL, related_name="certificates", null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(
                check=Q(Q(is_ca=False) | Q(parent_certificate__isnull=True)),
                name="isca_or_parentcertificate",
                violation_error_message="ca cert cannot have any parent cert",
            )
        ]

    def is_chain_complete(self) -> str | None:
        if not self.is_ca:
            if not self.parent_certificate:
                return f"parent_certificate does not exists on {str(self)}"
            return self.parent_certificate.is_chain_complete()

    def get_fullchain_content(self):
        if self.parent_certificate:
            return self.content + "\n" + self.parent_certificate.content
        return self.content

    def get_full_pem_content(self):
        if self.parent_certificate:
            return self.private_key.content + "\n" + self.content + "\n" + self.parent_certificate.content
        return self.private_key.content + "\n" + self.content


class CertbotInfo(TimeStampedModel, models.Model):
    class CertbotInfoQuerySet(models.QuerySet):
        def ann_valid_to(self):
            certificate_qs = Certificate.objects.filter(certbot_info=OuterRef("id")).order_by("-valid_to")
            return self.annotate(valid_to=Subquery(certificate_qs.values("valid_to")[:1]))

    uuid = models.UUIDField(db_index=True, unique=True)
    cert_name = models.CharField(max_length=255, unique=True, db_index=True)

    objects = CertbotInfoQuerySet.as_manager()

    def __str__(self):
        return f"{self.pk}-{self.cert_name}"

    @property
    def valid_to(self):
        return self._valid_to

    @valid_to.setter
    def valid_to(self, value):
        self._valid_to = value


class Domain(TimeStampedModel, models.Model):
    name = models.CharField(max_length=255, db_index=True, unique=True, validators=[validators.validate_domain_name])
    dns_provider = models.ForeignKey(
        "DNSProvider", on_delete=models.PROTECT, related_name="dnsprovider_domains", null=True, blank=True
    )
    is_root = models.BooleanField()
    root = models.ForeignKey("self", on_delete=models.PROTECT, related_name="subdomains", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            CheckConstraint(
                check=Q(Q(root__isnull=True) | Q(is_root=False)),
                name="either_root_or_isnotroot",
            )
        ]

    def __str__(self):
        return f"{self.pk}-{self.name}"

    def get_root(self):
        if not self.root and self.is_root:
            return self
        if not self.root and not self.is_root:
            return None
        return self.root.get_root()

    def clean(self):
        if self.root:
            if not self.name.endswith(self.root.name):
                raise ValidationError(gettext("name does not match with root"))

    def get_dns_provider(self):
        if dns_provider := self.dns_provider:
            return dns_provider
        if self.root:
            return self.root.get_dns_provider()


class DomainCertificate(TimeStampedModel, models.Model):
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="domain_domaincertificates")
    certificate = models.ForeignKey(
        Certificate, on_delete=models.CASCADE, related_name="certificate_domaincertificates"
    )

    def __str__(self):
        return f"{self.pk}-{self.domain}"


class CertificateTask(TimeStampedModel, models.Model):
    class TaskTypeChoices(models.IntegerChoices):
        ISSUE = 1
        RENEWAL = 2

    certbot_info_uuid = models.UUIDField()
    task_type = models.PositiveSmallIntegerField(choices=TaskTypeChoices.choices)
    logs = models.TextField(blank=True)
    is_closed = models.BooleanField()
    is_success = models.BooleanField(null=True, blank=True)

    def log(self, name: str, msg: str):
        self.logs = self.logs or ""
        time_str = timezone.now().astimezone(ZoneInfo("UTC"))
        self.logs += "\n" + f"{name} {time_str}: {msg}"
        self.save()


class DNSProvider(TimeStampedModel, models.Model):
    name = models.SlugField()
    provider_key = models.SlugField(max_length=127, db_index=True)
    provider_args = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.pk}-{self.name}"

    @property
    def provider_cls(self) -> type[BaseDNSProvider]:
        return [i for i in AVAILABLE_DNS_PROVIDERS if i.TYPE_IDENTIFIER == self.provider_key][0]

    def get_provider(self) -> BaseDNSProvider:
        return self.provider_cls(args=self.provider_args)


class UserDevice(TimeStampedModel, models.Model):
    user_agent = models.CharField(max_length=255)
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="userdevices")

    class Meta:
        ordering = ["-created_at"]
        constraints = [UniqueConstraint(fields=("user_agent", "user"), name="unique_user_useragent_for_userdevice")]
