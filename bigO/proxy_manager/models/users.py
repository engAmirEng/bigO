import datetime

from django.utils import timezone

from bigO.proxy_manager.subscription import AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS
from bigO.proxy_manager.subscription.base import BaseSubscriptionPlanProvider
from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import Case, Count, F, OuterRef, Q, Subquery, UniqueConstraint, When, Exists, Value
from django.db.models.functions import Coalesce


class Agency(TimeStampedModel, models.Model):
    name = models.SlugField()
    is_active = models.BooleanField()
    sublink_header_template = models.TextField(null=True, blank=False, help_text="{{ subscription_obj, expires_at }}")
    sublink_host = models.ForeignKey("core.Domain", on_delete=models.PROTECT, related_name="+", null=True, blank=False)

    def __str__(self):
        return f"{self.pk}-{self.name}"


class Agent(TimeStampedModel, models.Model):
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="user_agents")
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="agency_agents")
    is_active = models.BooleanField()

    class Meta:
        ordering = ["-created_at"]
        constraints = [UniqueConstraint(fields=("user", "agency"), name="unique_user_agency")]


class SubscriptionPlan(TimeStampedModel, models.Model):
    class SubscriptionPlanQuerySet(models.QuerySet):
        def ann_periods_count(self):
            from ..models import SubscriptionPeriod
            alive_profiles_qs = SubscriptionProfile.objects.filter(id=OuterRef("profile_id")).ann_is_alive().filter(is_alive=True)
            qs = SubscriptionPeriod.objects.filter(plan=OuterRef("id"), selected_as_current=True)
            alive_qs = qs.filter(Exists(alive_profiles_qs))
            return self.annotate(
                periods_count=Coalesce(
                    Subquery(qs.order_by().values("plan").annotate(count=Count("id")).values("count")), 0
                ),
                alive_periods_count=Coalesce(
                    Subquery(alive_qs.order_by().values("plan").annotate(count=Count("id")).values("count")), 0
                )
            )

    objects = SubscriptionPlanQuerySet.as_manager()

    name = models.SlugField()
    plan_provider_key = models.SlugField(max_length=127, db_index=True)
    plan_provider_args = models.JSONField(null=True, blank=True)
    connection_rule = models.ForeignKey(
        "ConnectionRule",
        on_delete=models.PROTECT,
        related_name="connectionrule_subscriptionplans",
    )
    capacity = models.PositiveIntegerField()

    @property
    def plan_provider_cls(self) -> type[BaseSubscriptionPlanProvider]:
        return [i for i in AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS if i.TYPE_IDENTIFIER == self.plan_provider_key][0]

    def __str__(self):
        return f"{self.pk}-{self.name}"


class AgencyPlanSpec(TimeStampedModel, models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="agency_agencyplanspecs")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.CASCADE, related_name="plan_agencyplanspecs")
    capacity = models.PositiveIntegerField()

    class Meta:
        constraints = [UniqueConstraint(fields=("agency", "plan"), name="unique_agency_plan")]


class SubscriptionPeriod(TimeStampedModel, models.Model):
    class SubscriptionPeriodQuerySet(models.QuerySet):
        def ann_expires_at(self):
            whens = []
            for i in AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS:
                ann_expr = i.get_expires_at_ann_expr()
                whens.append(When(plan__plan_provider_key=i.TYPE_IDENTIFIER, then=ann_expr))
            return self.annotate(expires_at=Case(*whens, output_field=models.DateTimeField()))

        def ann_up_bytes_remained(self):
            whens = []
            for i in AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS:
                ann_expr = i.get_up_bytes_remained_expr()
                whens.append(When(plan__plan_provider_key=i.TYPE_IDENTIFIER, then=ann_expr))
            return self.annotate(up_bytes_remained=Case(*whens, output_field=models.PositiveBigIntegerField()))

        def ann_dl_bytes_remained(self):
            whens = []
            for i in AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS:
                ann_expr = i.get_up_bytes_remained_expr()
                whens.append(When(plan__plan_provider_key=i.TYPE_IDENTIFIER, then=ann_expr))
            return self.annotate(dl_bytes_remained=Case(*whens, output_field=models.PositiveBigIntegerField()))

        def ann_total_limit_bytes(self):
            whens = []
            for i in AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS:
                ann_expr = i.get_total_limit_bytes_expr()
                whens.append(When(plan__plan_provider_key=i.TYPE_IDENTIFIER, then=ann_expr))
            return self.annotate(total_limit_bytes=Case(*whens, output_field=models.PositiveBigIntegerField()))

    plan = models.ForeignKey("SubscriptionPlan", on_delete=models.PROTECT, related_name="+")
    plan_args = models.JSONField(null=True, blank=True)
    profile = models.ForeignKey("SubscriptionProfile", on_delete=models.PROTECT, related_name="periods")

    selected_as_current = models.BooleanField()

    last_sublink_at = models.DateTimeField(null=True, blank=True)
    first_usage_at = models.DateTimeField(null=True, blank=True)
    last_usage_at = models.DateTimeField(null=True, blank=True)
    current_download_bytes = models.PositiveBigIntegerField(default=0)
    current_upload_bytes = models.PositiveBigIntegerField(default=0)
    flow_download_bytes = models.PositiveBigIntegerField(default=0)
    flow_upload_bytes = models.PositiveBigIntegerField(default=0)
    flow_point_at = models.DateTimeField(null=True, blank=True)
    last_flow_sync_at = models.DateTimeField(null=True, blank=True)

    objects = SubscriptionPeriodQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            UniqueConstraint(
                fields=("profile",), condition=Q(selected_as_current=True), name="one_selected_as_current_each_profile"
            )
        ]

    def __str__(self):
        return f"{self.pk}-|{self.profile}|{self.plan}"

    @property
    def xray_uuid(self):
        return self.profile.xray_uuid

    def xray_email(self):
        if self.profile.user_id:
            f"period{self.id}.profile{self.profile_id}.user{self.profile.user_id}@love.com"
        return f"period{self.id}.profile{self.profile_id}@love.com"

    @property
    def expires_at(self) -> datetime.datetime:
        return self._expires_at

    @expires_at.setter
    def expires_at(self, value):
        self._expires_at = value

    @property
    def dl_bytes_remained(self) -> int:
        return self._dl_bytes_remained

    @dl_bytes_remained.setter
    def dl_bytes_remained(self, value):
        self._dl_bytes_remained = value

    @property
    def up_bytes_remained(self) -> int:
        return self._up_bytes_remained

    @up_bytes_remained.setter
    def up_bytes_remained(self, value):
        self._up_bytes_remained = value

    @property
    def total_limit_bytes(self) -> int:
        return self._total_limit_bytes

    @total_limit_bytes.setter
    def total_limit_bytes(self, value):
        self._total_limit_bytes = value


class SubscriptionProfile(TimeStampedModel, models.Model):
    class SubscriptionProfileQuerySet(models.QuerySet):
        def ann_last_usage_at(self):
            subscriptionperiod_sub_qs = SubscriptionPeriod.objects.filter(profile=OuterRef("id")).order_by(
                F("last_usage_at").desc(nulls_last=True)
            )
            return self.annotate(last_usage_at=Subquery(subscriptionperiod_sub_qs.values("last_usage_at")[:1]))

        def ann_last_sublink_at(self):
            subscriptionperiod_sub_qs = SubscriptionPeriod.objects.filter(profile=OuterRef("id")).order_by(
                F("last_sublink_at").desc(nulls_last=True)
            )
            return self.annotate(last_sublink_at=Subquery(subscriptionperiod_sub_qs.values("last_sublink_at")[:1]))

        def ann_is_alive(self):
            now = timezone.now()
            return self.ann_last_usage_at().annotate(
                is_alive=Case(
                    When(last_usage_at__gt=now - datetime.timedelta(hours=24), then=Value(True)),
                    default=Value(False)
                ),

            )


    initial_agency = models.ForeignKey(
        "Agency", on_delete=models.PROTECT, related_name="initialagency_subscriptionprofiles", null=True, blank=False
    )  # nonull
    title = models.CharField(max_length=127)
    uuid = models.UUIDField(unique=True)
    user = models.ForeignKey("users.User", on_delete=models.PROTECT, null=True, blank=True)
    xray_uuid = models.UUIDField(blank=True, unique=True)
    description = models.TextField(max_length=4095, null=True, blank=True)
    is_active = models.BooleanField()

    objects = SubscriptionProfileQuerySet.as_manager()

    def __str__(self):
        return f"{self.pk}-{self.title}"

    @property
    def last_sublink_at(self):
        return self._last_sublink_at

    @last_sublink_at.setter
    def last_sublink_at(self, value):
        self._last_sublink_at = value

    @property
    def last_usage_at(self):
        return self._last_usage_at

    @last_usage_at.setter
    def last_usage_at(self, value):
        self._last_usage_at = value

    def get_sublink(self):
        if self.initial_agency.sublink_host:
            domain = self.initial_agency.sublink_host.name
        else:
            raise ValueError("sublink_host not set")
        return f"https://{domain}/sub/{self.uuid}"


class SubscriptionEvent(TimeStampedModel, models.Model):
    related_agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="+")
    agentuser = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="+")
    profile = models.ForeignKey(
        SubscriptionProfile, on_delete=models.CASCADE, related_name="profile_subscriptionevents"
    )
    period = models.ForeignKey(SubscriptionPeriod, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=255)
