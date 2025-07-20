import datetime

from bigO.proxy_manager.subscription import AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS
from bigO.proxy_manager.subscription.base import BaseSubscriptionPlanProvider
from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import Case, Count, F, OuterRef, Q, Subquery, UniqueConstraint, When
from django.db.models.functions import Coalesce


class SubscriptionPlanPrice(TimeStampedModel, models.Model):
    plan = models.ForeignKey("Sub")
