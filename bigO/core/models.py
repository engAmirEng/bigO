from polymorphic.models import PolymorphicModel

from bigO.utils.models import TimeStampedModel
from django.db import models


class CryptographicObject(PolymorphicModel, TimeStampedModel, models.Model):
    class AlgorithmChoices(models.IntegerChoices):
        RSA = 1, "RSA"
        ECDSA = 2, "ECDSA"

    slug = models.SlugField(unique=True)
    algorithm = models.PositiveSmallIntegerField(AlgorithmChoices.choices)
    fingerprint = models.CharField(max_length=64, blank=False, db_index=True)
    content = models.TextField()

    def __str__(self):
        return f"{self.pk}-{self.slug}"


class PrivateKey(CryptographicObject):
    passphrase = models.CharField(max_length=255, null=True, blank=True)
    key_length = models.PositiveSmallIntegerField()


class PublicKey(CryptographicObject):
    private_key = models.ForeignKey(PrivateKey, on_delete=models.CASCADE, null=True, blank=True)
    parent_public_key = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    subject = models.CharField(max_length=255)
    issuer = models.CharField(max_length=255)
