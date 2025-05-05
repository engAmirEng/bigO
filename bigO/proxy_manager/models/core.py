import datetime

from solo.models import SingletonModel

from bigO.proxy_manager.subscription import AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS
from bigO.proxy_manager.subscription.base import BaseSubscriptionPlanProvider
from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import Case, F, OuterRef, Q, Subquery, UniqueConstraint, When


class Config(TimeStampedModel, SingletonModel):
    nginx_config_http_template = models.TextField(null=True, blank=False, help_text="{{ node_obj }}")
    nginx_config_stream_template = models.TextField(null=True, blank=False, help_text="{{ node_obj }}")
    xray_config_template = models.TextField(
        null=True, blank=False, help_text="{{ node, inbound_parts, rule_parts, balancer_parts }}"
    )
    geosite = models.ForeignKey("node_manager.ProgramVersion", related_name="geosite_xrayconfig", on_delete=models.PROTECT, null=True, blank=True)
    geoip = models.ForeignKey("node_manager.ProgramVersion", related_name="geoip_xrayconfig", on_delete=models.PROTECT, null=True, blank=True)


class Region(TimeStampedModel, models.Model):
    name = models.SlugField()

    def __str__(self):
        return f"{self.pk}-{self.name}"


class ISP(TimeStampedModel, models.Model):
    name = models.SlugField()

    def __str__(self):
        return f"{self.pk}-{self.name}"


class OutboundGroup(TimeStampedModel, models.Model):
    name = models.SlugField(unique=True)

    def __str__(self):
        return f"{self.id}-{self.name}"


class NodeOutbound(TimeStampedModel, models.Model):
    name = models.SlugField()
    node = models.ForeignKey("node_manager.Node", on_delete=models.CASCADE, related_name="node_nodeoutbounds")
    group = models.ForeignKey(OutboundGroup, on_delete=models.CASCADE, related_name="group_nodeoutbounds")
    xray_outbound_template = models.TextField(help_text="{{ node }}")

    class Meta:
        constraints = [UniqueConstraint(fields=("name", "node"), name="unique_name_node")]

    def __str__(self):
        return f"{self.id}-{self.name}|{self.node}"


class ConnectionRule(TimeStampedModel, models.Model):
    name = models.SlugField()
    origin_region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name="originregion_connectionrules")
    destination_region = models.ForeignKey(
        Region, on_delete=models.CASCADE, related_name="destinationregion_connectionrules"
    )
    xray_rules_template = models.TextField(help_text="[RuleObject], {{ node, inbound_tags }}")

    def __str__(self):
        return f"{self.pk}-{self.name}"


class InboundType(TimeStampedModel, models.Model):
    is_active = models.BooleanField(default=True)
    is_template = models.BooleanField(default=False)
    name = models.SlugField()
    inbound_template = models.TextField(help_text="{{ node_obj, inbound_tag, consumers_part }}")
    consumer_obj_template = models.TextField(help_text="{{ subscriptionperiod_obj }}")
    link_template = models.TextField(blank=True, null=True, help_text="{{ subscriptionperiod_obj }}")
    nginx_path_config = models.TextField(blank=True, null=True)
    haproxy_backend = models.TextField(blank=True, null=True)
    haproxy_matcher_80 = models.TextField(blank=True, null=True)
    haproxy_matcher_443 = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.pk}-{self.name}"

# class InboundTypeFallback(TimeStampedModel, models.Model):
#     ref_type = models.ForeignKey(InboundType, on_delete=models.PROTECT, related_name="reftype_inboundtypefallback")
#     dest_type = models.ForeignKey(InboundType, on_delete=models.PROTECT, related_name="desttype_inboundtypefallback")

# class InboundGroup(TimeStampedModel, models.Model):
#     template = models.ForeignKey
#     inbound_groups = models.ManyToManyField("self")


class SubscriptionPlan(TimeStampedModel, models.Model):
    name = models.SlugField()
    plan_provider_key = models.SlugField(max_length=127, db_index=True)
    plan_provider_args = models.JSONField(null=True, blank=True)
    connection_rule = models.ForeignKey(
        ConnectionRule,
        on_delete=models.PROTECT,
        related_name="connectionrule_subscriptionplans",
    )

    @property
    def plan_provider_cls(self) -> type[BaseSubscriptionPlanProvider]:
        return [i for i in AVAILABLE_SUBSCRIPTION_PLAN_PROVIDERS if i.TYPE_IDENTIFIER == self.plan_provider_key][0]

    def __str__(self):
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
        constraints = [
            UniqueConstraint(
                fields=("profile",), condition=Q(selected_as_current=True), name="one_selected_as_current_each_profile"
            )
        ]

    def __str__(self):
        return f"{self.pk}-|{self.profile}|{self.plan}"

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


class SubscriptionNodeUsage(TimeStampedModel, models.Model):
    # to stats db
    subscription_oid = models.PositiveIntegerField()
    node_oid = models.PositiveIntegerField()
    upload_traffic = models.PositiveSmallIntegerField()
    download_traffic = models.PositiveSmallIntegerField()
