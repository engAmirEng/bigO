from solo.models import SingletonModel

from bigO.utils.models import TimeStampedModel
from django.core.exceptions import ValidationError
from django.db import models


class Config(SingletonModel):
    type1_formula = models.TextField()
    type2_formula = models.TextField(
        help_text="foroosh_record & kharid_record & ahrom_last_price => bazdeh & risk_percentage"
    )

    def get_type2_expressions_var(self):
        lines = self.type2_formula.split("\n")
        expressions_var = [i.split("=") for i in lines]
        expressions_var = [(i[0].strip(), i[1].strip()) for i in expressions_var]
        return expressions_var

    def clean(self):
        if self.type2_formula:
            try:
                expressions_var = self.get_type2_expressions_var()
            except Exception as e:
                raise ValidationError(e)
            vars = [i[0] for i in expressions_var]
            if "risk_percentage" not in vars:
                raise ValidationError("define risk_percentage")
            if "bazdeh" not in vars:
                raise ValidationError("define bazdeh")


class Ahrom(TimeStampedModel, models.Model):
    contract_num = models.CharField(max_length=255, unique=True)
    ekhtiar_kharid_inscodel = models.CharField(max_length=255, unique=True)
    ekhtiar_foroosh_inscodel = models.CharField(max_length=255, unique=True)
    strike_price = models.IntegerField()

    def __str__(self):
        return f"{self.id}-{self.contract_num}-{self.strike_price}"


class Type1Config(TimeStampedModel, models.Model):
    title = models.CharField(max_length=255, null=True, blank=True)
    ahrom = models.ForeignKey(Ahrom, on_delete=models.PROTECT, related_name="+")
    order = models.IntegerField()
    is_archived = models.BooleanField(default=False)

    def __str__(self):
        if self.title:
            return f"{self.id}-{self.title}-{self.ahrom.contract_num}"
        return f"{self.id}-{self.ahrom.contract_num}"


class Type2Config(TimeStampedModel, models.Model):
    title = models.CharField(max_length=255, null=True, blank=True)
    foroosh_ahrom = models.ForeignKey(Ahrom, on_delete=models.PROTECT, related_name="+")
    order = models.IntegerField()
    is_archived = models.BooleanField(default=False)

    def __str__(self):
        if self.title:
            return f"{self.id}-{self.title}-{self.foroosh_ahrom.contract_num}"
        return f"{self.id}-{self.foroosh_ahrom.contract_num}"


class Type2Relate(TimeStampedModel, models.Model):
    config = models.ForeignKey(Type2Config, on_delete=models.CASCADE, related_name="relates")
    kharid_ahrom = models.ForeignKey(Ahrom, on_delete=models.CASCADE, related_name="+")
    order = models.IntegerField()
