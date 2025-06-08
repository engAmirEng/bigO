from solo.models import SingletonModel

from bigO.utils.models import TimeStampedModel
from django.db import models


class Config(SingletonModel):
    type1_formula = models.TextField()
    type2_formula = models.TextField()

class Ahrom(TimeStampedModel, models.Model):
    contract_num = models.CharField(max_length=255, unique=True)
    ekhtiar_kharid_inscodel = models.CharField(max_length=255, unique=True)
    ekhtiar_foroosh_inscodel = models.CharField(max_length=255, unique=True)
    strike_price = models.IntegerField()

class Type1Config(TimeStampedModel, models.Model):
    ahrom = models.ForeignKey(Ahrom, on_delete=models.PROTECT, related_name="items")
    order = models.IntegerField()

class Type2Config(TimeStampedModel, models.Model):
    foroosh_ahrom = models.ForeignKey(Ahrom, on_delete=models.PROTECT, related_name="+")
    order = models.IntegerField()

class Type2Relate(TimeStampedModel, models.Model):
    config = models.ForeignKey(Type2Config, on_delete=models.CASCADE, related_name="items")
    kharid_ahrom = models.ForeignKey(Ahrom, on_delete=models.CASCADE, related_name="+")
    order = models.IntegerField()
