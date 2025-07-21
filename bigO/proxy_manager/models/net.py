import uuid
from types import SimpleNamespace

import django_jsonform.models.fields
from simple_history.models import HistoricalRecords
from solo.models import SingletonModel

from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import OuterRef, Subquery, Sum, UniqueConstraint
from django.db.models.functions import Coalesce


class RealitySpec(TimeStampedModel, models.Model):
    for_ip = models.ForeignKey("node_manager.PublicIP", on_delete=models.CASCADE, related_name="+")
    dest_ip = models.ForeignKey("node_manager.PublicIP", on_delete=models.CASCADE, related_name="+")
    dest_certificate_domain = models.ForeignKey("core.Domain", on_delete=models.CASCADE, related_name="+")
    dest_geo = models.ForeignKey("Region", on_delete=models.CASCADE, related_name="+")
    description = models.TextField(null=True, blank=True)
