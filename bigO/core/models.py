from solo.models import SingletonModel

from bigO.utils.models import TimeStampedModel
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import CheckConstraint, Q


class SiteConfiguration(SingletonModel):
    nodes_ca_cert = models.ForeignKey("Certificate", on_delete=models.PROTECT, null=True, blank=False)
    main_nginx = models.ForeignKey("node_manager.ProgramVersion", on_delete=models.PROTECT, null=True, blank=False)
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
