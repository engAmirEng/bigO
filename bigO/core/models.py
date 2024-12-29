from polymorphic.models import PolymorphicModel

from bigO.utils.models import TimeStampedModel
from django.db import models


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


class Certificate(PolymorphicModel, AbstractCryptographicObject, TimeStampedModel, models.Model):
    fingerprint = models.CharField(max_length=64, blank=False, db_index=True)
    private_key = models.ForeignKey(PrivateKey, on_delete=models.CASCADE, null=True, blank=True)
    ca_certificate = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    subject = models.CharField(max_length=255)
    issuer = models.CharField(max_length=255)
