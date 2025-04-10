from zoneinfo import ZoneInfo

from solo.models import SingletonModel

from bigO.utils.models import TimeStampedModel
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Q
from django.utils import timezone
from django.utils.translation import gettext

from .dns import AVAILABLE_DNS_PROVIDERS
from .dns.base import BaseDNSProvider


class LogActionType(models.IntegerChoices):
    NOTHING = 0, "nothing"
    TO_LOKI = 1, "to loki"


class SiteConfiguration(SingletonModel):
    nodes_ca_cert = models.ForeignKey("Certificate", on_delete=models.PROTECT, null=True, blank=False)
    main_nginx = models.ForeignKey(
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

    slug = models.SlugField(unique=True)
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

    class Meta:
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


class Domain(TimeStampedModel, models.Model):
    name = models.CharField(max_length=255, db_index=True, unique=True)
    dns_provider = models.ForeignKey(
        "DNSProvider", on_delete=models.PROTECT, related_name="dnsprovider_domains", null=True, blank=True
    )
    is_root = models.BooleanField()
    root = models.ForeignKey("self", on_delete=models.PROTECT, related_name="subdomains", null=True, blank=True)

    class Meta:
        constraints = [
            CheckConstraint(
                check=Q(Q(root__isnull=True) | Q(is_root=False)),
                name="either_root_or_isnotroot",
            )
        ]

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

    def __str__(self):
        return f"{self.pk}-{self.name}"


class DomainCertificate(TimeStampedModel, models.Model):
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="domain_domaincertificates")
    certificate = models.ForeignKey(
        Certificate, on_delete=models.CASCADE, related_name="certificate_domaincertificates"
    )

    def __str__(self):
        return f"{self.pk}-{self.domain}"


class CertbotCert(TimeStampedModel, models.Model):
    uuid = models.UUIDField(db_index=True, unique=True)
    certificate = models.OneToOneField(Certificate, on_delete=models.CASCADE, related_name="certificate_certbot")
    cert_name = models.CharField(max_length=255, unique=True, db_index=True)


class CertificateTask(TimeStampedModel, models.Model):
    class TaskTypeChoices(models.IntegerChoices):
        ISSUE = 1
        RENEWAL = 2

    # celery_task_id = models.CharField(max_length=255, unique=True)
    certbot_cert_uuid = models.UUIDField()
    task_type = models.PositiveSmallIntegerField(choices=TaskTypeChoices.choices)
    logs = models.TextField(blank=True)
    is_closed = models.BooleanField()
    is_success = models.BooleanField(null=True, blank=True)

    def log(self, name: str, msg: str):
        self.logs = self.logs or ""
        time_str = timezone.now().astimezone(ZoneInfo("UTC"))
        self.logs += "\n" + f"{name} {time_str}: {msg}"
        self.save()


#
# class CertificateTaskDomain(TimeStampedModel, models.Model):
#     certificate_task = models.ForeignKey(CertificateTask, on_delete=models.CASCADE, related_name="certificatetask_domains")
#     domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="domain_certificatetasks")


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
