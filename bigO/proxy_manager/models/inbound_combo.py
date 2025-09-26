from bigO.utils.models import TimeStampedModel
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import UniqueConstraint

from .. import typing

# class DomainProxyUsageSpec(TimeStampedModel, models.Model):
#     domain = models.ForeignKey("core.Domain", on_delete=models.CASCADE)
#     include_subs = models.BooleanField(default=True)
#     perspective_region = models.ForeignKey("proxy_manager.Region", on_delete=models.PROTECT, related_name="+")
#     out_clf = models.DecimalField(max_digits=4, decimal_places=2)
#     in_clf = models.DecimalField(max_digits=4, decimal_places=2)
#     out_any = models.DecimalField(max_digits=4, decimal_places=2)
#     in_any = models.DecimalField(max_digits=4, decimal_places=2)
#
#     class Meta:
#         constraints = [
#             UniqueConstraint(
#                 fields=("domain", "perspective_region"),
#                 name="unique_domainproxyusagespec_per_domain_region",
#                 violation_error_message="already exists with this perspective_region for this domain",
#             )
#         ]
#
#
# class IPProxyUsageSpec(models.Model):
#     public_ip = models.ForeignKey("node_manager.PublicIP", on_delete=models.CASCADE)
#     perspective_region = models.ForeignKey("proxy_manager.Region", on_delete=models.PROTECT, related_name="+")
#     out_clf = models.DecimalField(max_digits=4, decimal_places=2)
#     in_clf = models.DecimalField(max_digits=4, decimal_places=2)
#     out_any = models.DecimalField(max_digits=4, decimal_places=2)
#     in_any = models.DecimalField(max_digits=4, decimal_places=2)
#
#
#     class Meta:
#         constraints = [
#             UniqueConstraint(
#                 fields=("public_ip", "perspective_region"),
#                 name="unique_domainproxyusagespec_per_public_ip_region",
#                 violation_error_message="already exists with this perspective_region for this public_ip",
#             )
#         ]


class InboundSpec(TimeStampedModel, models.Model):
    name = models.SlugField(unique=True)
    inbound_type = models.ForeignKey("InboundType", on_delete=models.CASCADE, related_name="inboundtype_combinations")
    port = models.PositiveSmallIntegerField()
    domain_address = models.ForeignKey(
        "net_manager.DNSRecord", on_delete=models.CASCADE, related_name="+", null=True, blank=True
    )
    ip_address = models.ForeignKey(
        "node_manager.PublicIP", on_delete=models.CASCADE, related_name="+", null=True, blank=True
    )
    domain_sni = models.ForeignKey(
        "core.Domain",
        on_delete=models.CASCADE,
        related_name="domainsni_inboundflatcombinations",
        null=True,
        blank=True,
    )
    domainhost_header = models.ForeignKey(
        "core.Domain",
        on_delete=models.CASCADE,
        related_name="domainhostheader_inboundflatcombinations",
        null=True,
        blank=True,
    )
    reality = models.ForeignKey("RealitySpec", on_delete=models.CASCADE, related_name="+", null=True, blank=True)

    def __str__(self):
        try:
            combo_stat = self.get_combo_stat()
        except Exception:
            return f"{self.pk}-{self.name}|error"
        return f"{self.pk}-{self.name}|{combo_stat.address}:{combo_stat.port}:{combo_stat.sni or combo_stat.domainhostheader}"

    def clean(self):
        try:
            self.get_combo_stat()
        except Exception as e:
            raise ValidationError(f"failed to get_combo_stat, {str(e)}")

    def get_combo_stat(self):
        if self.domain_address:
            address = self.domain_address.domain.name
        elif self.ip_address:
            address = self.ip_address.ip.ip
        elif self.reality:
            address = self.reality.for_ip.ip.ip
        else:
            raise NotImplementedError

        if self.port:
            port = self.port
        elif self.reality:
            port = self.reality.port
        else:
            raise NotImplementedError

        if self.domain_sni:
            sni = self.domain_sni.name
        elif self.reality:
            sni = self.reality.certificate_domain.name
        else:
            sni = None

        if self.domainhost_header:
            domainhost_header = self.domainhost_header.name
        else:
            domainhost_header = None

        return typing.ComboStat(
            **{
                "address": address,
                "port": self.port,
                "sni": sni,
                "domainhostheader": domainhost_header,
            }
        )
