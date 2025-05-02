from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import UniqueConstraint


class Agency(TimeStampedModel, models.Model):
    name = models.SlugField()
    sublink_header_template = models.TextField(null=True, blank=False, help_text="{{ subscription_obj, expires_at }}")
    is_active = models.BooleanField()

    def __str__(self):
        return f"{self.pk}-{self.name}"


class Agent(TimeStampedModel, models.Model):
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="user_agents")
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="agency_agents")
    is_active = models.BooleanField()

    class Meta:
        constraints = [UniqueConstraint(fields=("user", "agency"), name="unique_user_agency")]
