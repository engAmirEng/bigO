from django.db.models import CheckConstraint
from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import Q
from bigO.core.dns import RecordType

class DNSRecord(TimeStampedModel, models.Model):
    class TypeChoices(models.IntegerChoices):
        A = 1, "A"
        AAAA = 2, "AAAA"
        CNAME = 3, "CNAME"

        def to_record_type(self):
            return RecordType(self.name)

    provider_sync_at = models.DateTimeField(null=True, blank=True)
    id_provider = models.CharField(max_length=255, null=True, blank=True)
    domain = models.ForeignKey("core.Domain", on_delete=models.CASCADE, related_name="domain_dnsrecords")
    type = models.PositiveSmallIntegerField(choices=TypeChoices.choices)
    proxied = models.BooleanField(default=False)
    value_ip = models.ForeignKey("node_manager.PublicIP", on_delete=models.CASCADE, related_name="+", null=True, blank=True)
    value_domain = models.ForeignKey("core.Domain", on_delete=models.CASCADE, related_name="value_domain_dnsrecords", null=True, blank=True)

    class Meta:
        constraints = [
            CheckConstraint(
                condition=Q(value_ip__isnull=True, value_domain__isnull=False) | Q(value_ip__isnull=False, value_domain__isnull=True),
                name="valueip_or_valuedomain_dnsrecord"
            )
        ]
