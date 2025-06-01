import humanize.filesize
from solo.admin import SingletonModelAdmin

from django.contrib import admin
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.urls import reverse
from django.utils.html import format_html

from . import forms, models


@admin.register(models.Config)
class ConfigModelAdmin(SingletonModelAdmin):
    list_display = ("__str__",)


@admin.register(models.Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("__str__",)


@admin.register(models.ISP)
class ISPAdmin(admin.ModelAdmin):
    list_display = ("__str__",)


class AgentInline(admin.StackedInline):
    extra = 1
    model = models.Agent
    autocomplete_fields = ("user",)


@admin.register(models.Agency)
class AgencyModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
    search_fields = ("name",)
    inlines = (AgentInline,)


@admin.register(models.Agent)
class AgentModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "agency", "is_active")
    autocomplete_fields = ("user", "agency")


@admin.register(models.SubscriptionProfile)
class SubscriptionProfileModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "initial_agency", "user", "last_usage_at", "last_sublink_at")
    list_editable = []
    form = forms.SubscriptionProfileModelForm
    autocomplete_fields = ("user",)
    search_fields = ("title", "user__name", "description", "uuid", "xray_uuid")

    def get_queryset(self, request):
        return super().get_queryset(request).ann_last_usage_at().ann_last_sublink_at()

    @admin.display(ordering="last_usage_at")
    def last_usage_at(self, obj):
        if obj.last_usage_at is None:
            return "never"
        return naturaltime(obj.last_usage_at)

    @admin.display(ordering="last_sublink_at")
    def last_sublink_at(self, obj):
        if obj.last_sublink_at is None:
            return "never"
        return naturaltime(obj.last_sublink_at)


@admin.register(models.SubscriptionPlan)
class SubscriptionPlanModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
    form = forms.SubscriptionPlanModelForm


@admin.register(models.SubscriptionPeriod)
class SubscriptionPeriodModelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "profile_display",
        "plan_display",
        "selected_as_current",
        "first_usage_at_display",
        "last_usage_at_display",
        "last_sublink_at_display",
        "current_download_bytes_display",
        "current_upload_bytes_display",
        "expires_at",
        "up_bytes_remained",
        "dl_bytes_remained",
    )
    form = forms.SubscriptionPeriodModelForm
    autocomplete_fields = ("profile",)
    search_fields = (
        "profile__title",
        "profile__user__name",
        "profile__description",
        "profile__uuid",
        "profile__xray_uuid",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("profile", "plan")
            .ann_expires_at()
            .ann_dl_bytes_remained()
            .ann_up_bytes_remained()
        )

    @admin.display(ordering="profile")
    def profile_display(self, obj):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("admin:proxy_manager_subscriptionprofile_change", args=[obj.profile.id]),
            str(obj.profile),
        )

    @admin.display(ordering="plan")
    def plan_display(self, obj):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("admin:proxy_manager_subscriptionplan_change", args=[obj.plan.id]),
            str(obj.plan),
        )

    @admin.display(ordering="dl_bytes_remained")
    def dl_bytes_remained(self, obj):
        return humanize.filesize.naturalsize(obj.dl_bytes_remained)

    @admin.display(ordering="up_bytes_remained")
    def up_bytes_remained(self, obj):
        return humanize.filesize.naturalsize(obj.up_bytes_remained)

    @admin.display(ordering="current_upload_bytes")
    def current_upload_bytes_display(self, obj):
        return humanize.filesize.naturalsize(obj.current_upload_bytes)

    @admin.display(ordering="current_download_bytes")
    def current_download_bytes_display(self, obj):
        return humanize.filesize.naturalsize(obj.current_download_bytes)

    @admin.display(ordering="first_usage_at", description="first usage at")
    def first_usage_at_display(self, obj):
        if obj.first_usage_at is None:
            return "never"
        return naturaltime(obj.first_usage_at)

    @admin.display(ordering="last_usage_at", description="last usage at")
    def last_usage_at_display(self, obj):
        if obj.last_usage_at is None:
            return "never"
        return naturaltime(obj.last_usage_at)

    @admin.display(ordering="last_sublink_at", description="last sublink at")
    def last_sublink_at_display(self, obj):
        if obj.last_sublink_at is None:
            return "never"
        return naturaltime(obj.last_sublink_at)


@admin.register(models.NodeOutbound)
class NodeOutboundModelAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "rule", "node", "to_inbound_type", "inbound_spec")
    search_fields = ("name", "xray_outbound_template")
    list_filter = ("to_inbound_type", "rule")


class RuleNodeOutboundInline(admin.StackedInline):
    extra = 0
    model = models.NodeOutbound
    autocomplete_fields = ("rule", "node", "inbound_spec")
    ordering = ("node", "-created_at")


class ConnectionRuleInboundSpecInline(admin.StackedInline):
    extra = 0
    model = models.ConnectionRuleInboundSpec
    autocomplete_fields = ("spec",)


@admin.register(models.ConnectionRule)
class ConnectionRuleModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
    inlines = (RuleNodeOutboundInline, ConnectionRuleInboundSpecInline)
    search_fields = ("name", "xray_rules_template")


@admin.register(models.InternalUser)
class InternalUserModelAdmin(admin.ModelAdmin):
    list_display = ("id", "node", "connection_rule", "is_active", "first_usage_at", "last_usage_at")
    list_filter = ("node",)
    search_fields = ("xray_uuid",)
    form = forms.InternalUserModelForm
    autocomplete_fields = ("node", "connection_rule")


class InboundComboInline(admin.StackedInline):
    extra = 0
    model = models.InboundCombo


class NodeOutboundInline(admin.StackedInline):
    extra = 0
    model = models.NodeOutbound
    autocomplete_fields = ("rule", "node", "inbound_spec")
    ordering = ("rule", "-created_at")


@admin.register(models.InboundType)
class InboundTypeModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "is_active", "is_template")
    search_fields = ("name", "inbound_template")
    inlines = (InboundComboInline, NodeOutboundInline)


class InboundComboChoiceGroupInline(admin.StackedInline):
    extra = 1
    model = models.InboundComboChoiceGroup
    autocomplete_fields = ("combo",)


@admin.register(models.InboundComboGroup)
class InboundComboGroupModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
    inlines = (InboundComboChoiceGroupInline,)


class InboundComboDomainAddressInline(admin.TabularInline):
    extra = 0
    model = models.InboundComboDomainAddress
    autocomplete_fields = ("domain",)


class InboundComboIPAddressInline(admin.TabularInline):
    extra = 0
    model = models.InboundComboIPAddress
    autocomplete_fields = ("ip",)


class InboundComboDomainSniInline(admin.TabularInline):
    extra = 0
    model = models.InboundComboDomainSni
    autocomplete_fields = ("domain",)


class InboundComboDomainHostHeaderInline(admin.TabularInline):
    extra = 0
    model = models.InboundComboDomainHostHeader
    autocomplete_fields = ("domain",)


@admin.register(models.InboundCombo)
class InboundComboModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "inbound_type_display", "ports")
    list_select_related = ("inbound_type",)
    list_filter = ("inbound_type",)
    search_fields = ("name", "inbound_type__name")
    autocomplete_fields = ("inbound_type",)
    inlines = (
        InboundComboDomainAddressInline,
        InboundComboIPAddressInline,
        InboundComboDomainSniInline,
        InboundComboDomainHostHeaderInline,
    )

    @admin.display(ordering="inbound_type")
    def inbound_type_display(self, obj):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("admin:proxy_manager_inboundtype_change", args=[obj.inbound_type.id]),
            str(obj.inbound_type),
        )


class ConnectionRuleInboundSpec(admin.StackedInline):
    model = models.ConnectionRuleInboundSpec
    extra = 0


class InboundSpecNodeOutboundInline(admin.StackedInline):
    model = models.NodeOutbound
    extra = 0
    autocomplete_fields = ("rule", "node", "inbound_spec")
    ordering = ("rule", "-created_at")
    show_change_link = True


@admin.register(models.InboundSpec)
class InboundSpecModelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "inbound_type",
        "port",
        "domain_address",
        "ip_address",
        "domain_sni",
        "domainhost_header",
    )
    list_select_related = ("inbound_type",)
    list_filter = ("inbound_type",)
    search_fields = (
        "name",
        "inbound_type__name",
        "domain_address__domain__name",
        "ip_address__ip",
        "domain_sni__name",
    )
    autocomplete_fields = ("domain_address", "ip_address", "domain_sni", "domainhost_header")
    inlines = (InboundSpecNodeOutboundInline, ConnectionRuleInboundSpec)

    @admin.display(ordering="inbound_type")
    def inbound_type_display(self, obj):
        return format_html(
            "<a href='{}'>{}</a>",
            reverse("admin:proxy_manager_inboundtype_change", args=[obj.inbound_type.id]),
            str(obj.inbound_type),
        )
