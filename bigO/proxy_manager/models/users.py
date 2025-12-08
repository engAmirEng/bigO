import datetime

import pydantic
from djmoney.models.fields import CurrencyField
from djmoney.settings import CURRENCY_CHOICES
from moneyed import get_currency
from taggit.managers import TaggableManager

from bigO.proxy_manager.subscription import AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS
from bigO.proxy_manager.subscription.base import BaseSubscriptionPlanProvider
from bigO.utils import calander_type
from bigO.utils.models import TimeStampedModel
from django.contrib.postgres.aggregates import ArrayAgg
from django.db import models
from django.db.models import Case, Count, Exists, F, OuterRef, Prefetch, Q, Subquery, UniqueConstraint, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone


class Agency(TimeStampedModel, models.Model):
    name = models.SlugField()
    is_active = models.BooleanField()
    sublink_header_template = models.TextField(null=True, blank=False, help_text="{{ subscription_obj, expires_at }}")
    sublink_host = models.ForeignKey("core.Domain", on_delete=models.PROTECT, related_name="+", null=True, blank=False)
    default_timezone = models.CharField(max_length=255, null=True, blank=True)
    default_language = models.CharField(max_length=3, null=True, blank=True)
    default_calendar_type = models.CharField(
        max_length=15, choices=calander_type.CalendarType.choices, null=True, blank=True
    )

    def __str__(self):
        return f"{self.pk}-{self.name}"


class Agent(TimeStampedModel, models.Model):
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="user_agents")
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="agency_agents")
    is_active = models.BooleanField()

    class Meta:
        ordering = ["-created_at"]
        constraints = [UniqueConstraint(fields=("user", "agency"), name="unique_user_agency")]


class AgencyPlanRestriction(TimeStampedModel, models.Model):
    class AgencyPlanRestrictionQuerySet(models.QuerySet):
        def ann_remained_count(self):
            return self.annotate(remained_count=F("capacity"))

    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="+")
    connection_rule = models.ForeignKey(
        "ConnectionRule",
        on_delete=models.CASCADE,
        related_name="+",
    )
    capacity = models.PositiveIntegerField()

    objects = AgencyPlanRestrictionQuerySet.as_manager()


class SubscriptionPlan(TimeStampedModel, models.Model):
    class SubscriptionPlanQuerySet(models.QuerySet):
        def ann_periods_count(self):
            from ..models import SubscriptionPeriod

            alive_profiles_qs = (
                SubscriptionProfile.objects.filter(id=OuterRef("profile_id")).ann_is_alive().filter(is_alive=True)
            )
            qs = SubscriptionPeriod.objects.filter(plan=OuterRef("id"), selected_as_current=True)
            alive_qs = qs.filter(Exists(alive_profiles_qs))
            return self.annotate(
                periods_count=Coalesce(
                    Subquery(qs.order_by().values("plan").annotate(count=Count("id")).values("count")), 0
                ),
                alive_periods_count=Coalesce(
                    Subquery(alive_qs.order_by().values("plan").annotate(count=Count("id")).values("count")), 0
                ),
            )

        def ann_remained_count(self):
            return self.annotate(remained_count=F("capacity"))

    objects = SubscriptionPlanQuerySet.as_manager()

    name = models.CharField(max_length=127)
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="+", null=True)  # todo migrate null
    is_active = models.BooleanField(default=True)
    plan_provider_key = models.SlugField(max_length=127, db_index=True)
    plan_provider_args = models.JSONField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    base_currency = CurrencyField(
        choices=CURRENCY_CHOICES, null=True, blank=False, help_text="currency unit that other prices are based on"
    )
    connection_rule = models.ForeignKey(
        "ConnectionRule",
        on_delete=models.PROTECT,
        related_name="connectionrule_subscriptionplans",
    )
    allowed_agencyusergroups = models.ManyToManyField("AgencyUserGroup", related_name="+", blank=True)
    capacity = models.PositiveIntegerField()
    tags = TaggableManager(related_name="+", blank=True)

    @property
    def plan_provider_cls(self) -> type[BaseSubscriptionPlanProvider]:
        return [i for i in AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS if i.TYPE_IDENTIFIER == self.plan_provider_key][0]

    @property
    def plan_display(self) -> str:
        plan_provider_cls = self.plan_provider_cls
        if plan_provider_cls.ProviderArgsModel and self.plan_provider_args:
            try:
                return plan_provider_cls.ProviderArgsModel(**self.plan_provider_args).title(
                    get_currency(self.base_currency)
                )
            except pydantic.ValidationError:
                return "Nan"

    @property
    def plan_verbose_display(self) -> str:
        plan_provider_cls = self.plan_provider_cls
        if plan_provider_cls.ProviderArgsModel and self.plan_provider_args:
            return plan_provider_cls.ProviderArgsModel(**self.plan_provider_args).verbose_title(
                get_currency(self.base_currency)
            )

    def __str__(self):
        if plan_display := self.plan_display:
            return f"{self.pk}-{self.name}({plan_display})"
        return f"{self.pk}-{self.name}"


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

        def ann_limit_passed_type(self, base_bytes=0, base_time=None):
            ann_name = "limit_passed_type" if (base_bytes == 0 and base_time is None) else "near_limit_passed_type"
            base_time = base_time or timezone.now()
            return (
                self.ann_expires_at()
                .ann_dl_bytes_remained()
                .ann_up_bytes_remained()
                .annotate(
                    **{
                        ann_name: Case(
                            When(
                                condition=Q(
                                    Q(up_bytes_remained__lte=base_bytes) | Q(dl_bytes_remained__lte=base_bytes)
                                ),
                                then=Value("traffic_limit"),
                            ),
                            When(
                                condition=Q(expires_at__lt=base_time),
                                then=Value("expired"),
                            ),
                            default=Value(None),
                        )
                    }
                )
            )

    plan = models.ForeignKey("SubscriptionPlan", on_delete=models.PROTECT, related_name="+")
    plan_args = models.JSONField(null=True, blank=True)
    profile = models.ForeignKey("SubscriptionProfile", on_delete=models.PROTECT, related_name="periods")

    selected_as_current = models.BooleanField()
    limited_at = models.DateTimeField(null=True, blank=True)

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
        def ann_telebot_tusers_ids(self):
            from bigO.telegram_bot.models import TelegramUser

            qs1 = TelegramUser.objects.filter(
                bot=OuterRef("initial_agency__agency_teleportpanels__bot"), user=OuterRef("user")
            )
            return self.annotate(
                telebot_tusers_ids=Subquery(
                    qs1.order_by().values("bot", "user").annotate(ids=ArrayAgg("id")).values("ids")
                )
            )

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
                    When(last_usage_at__gt=now - datetime.timedelta(hours=24), then=Value(True)), default=Value(False)
                ),
            )

        def ann_current_period_fields(self):
            period_qs = (
                SubscriptionPeriod.objects.filter(selected_as_current=True, profile_id=OuterRef("id"))
                .ann_expires_at()
                .ann_total_limit_bytes()
                .ann_limit_passed_type()
            )
            return self.annotate(
                current_total_limit_bytes=Subquery(period_qs.values("total_limit_bytes")[:1]),
                current_download_bytes=Subquery(period_qs.values("current_download_bytes")[:1]),
                current_upload_bytes=Subquery(period_qs.values("current_upload_bytes")[:1]),
                current_expires_at=Subquery(period_qs.values("expires_at")[:1]),
                current_created_at=Subquery(period_qs.values("created_at")[:1]),
                current_limit_passed_type=Subquery(period_qs.values("limit_passed_type")[:1]),
            )

    initial_agency = models.ForeignKey(
        "Agency", on_delete=models.PROTECT, related_name="initialagency_subscriptionprofiles", null=True, blank=False
    )  # nonull
    title = models.CharField(max_length=127)
    uuid = models.UUIDField(unique=True)
    user = models.ForeignKey("users.User", on_delete=models.PROTECT, null=True, blank=True)
    send_notifications = models.BooleanField(default=True)
    xray_uuid = models.UUIDField(blank=True, unique=True)
    description = models.TextField(max_length=4095, null=True, blank=True)
    is_active = models.BooleanField()

    objects = SubscriptionProfileQuerySet.as_manager()

    def __str__(self):
        return f"{self.pk}-{self.title}"

    async def get_current_period(self, related: tuple["str"] = None) -> SubscriptionPeriod | None:
        qs = self.periods.filter(selected_as_current=True)
        if related:
            qs = qs.select_related(*related)
        return await qs.afirst()

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

    def is_online(self):
        return self.last_usage_at and ((timezone.now() - self.last_usage_at) < datetime.timedelta(minutes=2))

    def get_sublink(self):
        if self.initial_agency.sublink_host:
            domain = self.initial_agency.sublink_host.name
        else:
            raise ValueError("sublink_host not set")
        return f"https://{domain}/sub/{self.uuid}/"


class ReferLink(TimeStampedModel, models.Model):
    class ReferLinkQuerySet(models.QuerySet):
        def ann_used_count(self):
            return self.annotate(used_count=Count("linkreferredby_agencyuser"))

        def ann_remainded_cap_count(self):
            return self.ann_used_count().annotate(remainded_cap_count=F("capacity") - F("used_count"))

    secret = models.CharField(max_length=255, unique=True)
    agency_user = models.ForeignKey("AgencyUser", on_delete=models.CASCADE, related_name="agencyuser_referlinks")
    capacity = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    objects = ReferLinkQuerySet.as_manager()


class AgencyUser(TimeStampedModel, models.Model):
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="+")
    agency = models.ForeignKey("Agency", on_delete=models.CASCADE, related_name="+")
    link_referred_by = models.ForeignKey(
        ReferLink, on_delete=models.PROTECT, related_name="linkreferredby_agencyuser", null=True, blank=True
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [UniqueConstraint(fields=("user", "agency"), name="unique_user_agency_agencyuser")]

    def __str__(self):
        return f"{self.pk}-@{self.user.username} ({self.agency.name})"


class AgencyUserGroup(TimeStampedModel, models.Model):
    class AgencyUserGroupQuerySet(models.QuerySet):
        def ann_members_count(self):
            return self.annotate(_members_count=Count("users"))

    name = models.CharField(max_length=127)
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="+", null=True, blank=True)
    users = models.ManyToManyField("users.User", blank=True)

    objects = AgencyUserGroupQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [UniqueConstraint(fields=("name", "agency"), name="unique_name_agency__agencyusergroup")]

    def __str__(self):
        return f"{self.pk}-{self.name}"

    @property
    def members_count(self):
        return self._members_count

    @members_count.setter
    def members_count(self, value):
        self._members_count = value


class SubscriptionEvent(TimeStampedModel, models.Model):
    related_agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="+")
    agentuser = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="+")
    profile = models.ForeignKey(
        SubscriptionProfile, on_delete=models.CASCADE, related_name="profile_subscriptionevents"
    )
    period = models.ForeignKey(SubscriptionPeriod, on_delete=models.CASCADE, null=True, blank=True)
    title = models.CharField(max_length=255)
