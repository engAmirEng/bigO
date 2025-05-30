from bigO.utils.models import TimeStampedModel
from django.core import validators
from django.db import models


class InboundComboGroup(TimeStampedModel, models.Model):
    name = models.SlugField(unique=True)

    def __str__(self):
        return f"{self.pk}-{self.name}"


class InboundComboChoiceGroup(TimeStampedModel, models.Model):
    group = models.ForeignKey(InboundComboGroup, on_delete=models.CASCADE, related_name="+")
    combo = models.ForeignKey("InboundCombo", on_delete=models.PROTECT, related_name="+")
    count = models.PositiveSmallIntegerField()
    ordering = models.PositiveSmallIntegerField()


class InboundCombo(TimeStampedModel, models.Model):
    name = models.SlugField(unique=True)
    inbound_type = models.ForeignKey("InboundType", on_delete=models.CASCADE, related_name="inboundtype_combos")
    ports = models.CharField(max_length=255, validators=[validators.validate_comma_separated_integer_list])

    def __str__(self):
        return f"{self.pk}-{self.name}"


class InboundComboDomainAddress(TimeStampedModel, models.Model):
    combo = models.ForeignKey(InboundCombo, on_delete=models.CASCADE, related_name="domainaddresses")
    domain = models.ForeignKey("core.Domain", on_delete=models.CASCADE, related_name="+")
    weight = models.PositiveSmallIntegerField()


class InboundComboIPAddress(TimeStampedModel, models.Model):
    combo = models.ForeignKey(InboundCombo, on_delete=models.CASCADE, related_name="ipaddresses")
    ip = models.ForeignKey("node_manager.PublicIP", on_delete=models.CASCADE, related_name="+")
    weight = models.PositiveSmallIntegerField()


class InboundComboDomainSni(TimeStampedModel, models.Model):
    combo = models.ForeignKey(InboundCombo, on_delete=models.CASCADE, related_name="domainsnis")
    domain = models.ForeignKey("core.Domain", on_delete=models.CASCADE, related_name="+")
    weight = models.PositiveSmallIntegerField()


class InboundComboDomainHostHeader(TimeStampedModel, models.Model):
    combo = models.ForeignKey(InboundCombo, on_delete=models.CASCADE, related_name="domainhostheaders")
    domain = models.ForeignKey("core.Domain", on_delete=models.CASCADE, related_name="+")
    weight = models.PositiveSmallIntegerField()


class InboundSpec(TimeStampedModel, models.Model):
    name = models.SlugField(unique=True)
    inbound_type = models.ForeignKey("InboundType", on_delete=models.CASCADE, related_name="inboundtype_combinations")
    port = models.PositiveSmallIntegerField()
    domain_address = models.ForeignKey("net_manager.DNSRecord", on_delete=models.CASCADE, related_name="+", null=True, blank=True)
    ip_address = models.ForeignKey("node_manager.PublicIP", on_delete=models.CASCADE, related_name="+", null=True, blank=True)
    domain_sni = models.ForeignKey("core.Domain", on_delete=models.CASCADE, related_name="domainsni_inboundflatcombinations", null=True, blank=True)
    domainhost_header = models.ForeignKey("core.Domain", on_delete=models.CASCADE, related_name="domainhostheader_inboundflatcombinations", null=True, blank=True)


    def __str__(self):
        return f"{self.pk}-{self.name}|{self.inbound_type}"
