from solo.admin import SingletonModelAdmin

from django.contrib import admin
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.template.defaultfilters import filesizeformat

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


@admin.register(models.Agency)
class AgencyModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
    search_fields = ("name",)


@admin.register(models.Agent)
class AgentModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
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
        "profile",
        "plan",
        "selected_as_current",
        "first_usage_at_display",
        "last_usage_at_display",
        "last_sublink_at_display",
        "current_download_bytes",
        "current_upload_bytes",
        "expires_at",
        "up_bytes_remained",
        "dl_bytes_remained",
    )
    form = forms.SubscriptionPeriodModelAdmin
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

    @admin.display(ordering="dl_bytes_remained")
    def dl_bytes_remained(self, obj):
        return filesizeformat(obj.dl_bytes_remained)

    @admin.display(ordering="up_bytes_remained")
    def up_bytes_remained(self, obj):
        return filesizeformat(obj.up_bytes_remained)

    @admin.display(ordering="current_upload_bytes")
    def current_upload_bytes(self, obj):
        return filesizeformat(obj.current_upload_bytes)

    @admin.display(ordering="current_download_bytes")
    def current_download_bytes(self, obj):
        return filesizeformat(obj.current_download_bytes)

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


class NodeOutboundInline(admin.StackedInline):
    extra = 0
    model = models.NodeOutbound


@admin.register(models.OutboundGroup)
class OutboundGroupModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
    inlines = [NodeOutboundInline]


@admin.register(models.NodeOutbound)
class NodeOutboundModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)


@admin.register(models.ConnectionRule)
class ConnectionRuleModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)


@admin.register(models.Inbound)
class InboundModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
