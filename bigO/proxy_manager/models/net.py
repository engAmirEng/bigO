from bigO.utils.models import TimeStampedModel
from django.db import models


class RealitySpec(TimeStampedModel, models.Model):
    port = models.PositiveSmallIntegerField()
    for_ip = models.ForeignKey("node_manager.PublicIP", on_delete=models.CASCADE, related_name="+")
    dest_ip = models.ForeignKey(
        "node_manager.PublicIP", on_delete=models.CASCADE, related_name="+", blank=True, null=True
    )
    certificate_domain = models.ForeignKey("core.Domain", on_delete=models.CASCADE, related_name="+")
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.id}-{self.certificate_domain.name}"
