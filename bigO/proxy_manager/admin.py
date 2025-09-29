import humanize.filesize
from simple_history.admin import SimpleHistoryAdmin
from solo.admin import SingletonModelAdmin

from bigO.utils.admin import admin_obj_change_url
from django.contrib import admin
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html

from . import forms, models, services


@admin.register(models.Config)
class ConfigModelAdmin(
    SimpleHistoryAdmin,
    SingletonModelAdmin,
):
    list_display = ("__str__",)
    autocomplete_fields = ("geosite", "geoip")


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
    ordering = ("created_at",)


@admin.register(models.Agency)
class AgencyModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
    search_fields = ("name",)
    inlines = (AgentInline,)
    autocomplete_fields = ("sublink_host",)


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


class AgencyPlanSpecInline(admin.StackedInline):
    model = models.AgencyPlanSpec
    extra = 0
    autocomplete_fields = ("agency",)
    ordering = ("created_at",)


@admin.register(models.SubscriptionPlan)
class SubscriptionPlanModelAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "connection_rule_display",
        "capacity",
        "periods_count_display",
        "alive_periods_count_display",
    )
    list_select_related = ("connection_rule",)
    list_filter = ("connection_rule",)
    form = forms.SubscriptionPlanModelForm
    inlines = (AgencyPlanSpecInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).ann_periods_count()

    @admin.display(ordering="periods_count")
    def periods_count_display(self, obj):
        return obj.periods_count

    @admin.display(ordering="alive_periods_count")
    def alive_periods_count_display(self, obj):
        return obj.alive_periods_count

    @admin.display(ordering="connection_rule")
    def connection_rule_display(self, obj):
        return obj.connection_rule and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.connection_rule),
            str(obj.connection_rule),
        )


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
    search_fields = (
        "profile__title",
        "profile__user__name",
        "profile__description",
        "profile__uuid",
        "profile__xray_uuid",
    )
    list_filter = ("selected_as_current", "plan", "plan__connection_rule")
    form = forms.SubscriptionPeriodModelForm
    autocomplete_fields = ("profile",)

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
        return obj.profile and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.profile),
            str(obj.profile),
        )

    @admin.display(ordering="plan")
    def plan_display(self, obj):
        return obj.plan and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.plan),
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


class OutboundConnectorInline(admin.StackedInline):
    extra = 0
    model = models.OutboundConnector
    autocomplete_fields = ("outbound_type", "inbound_spec", "dest_node")
    ordering = ("created_at",)
    show_change_link = True


@admin.register(models.OutboundType)
class OutboundTypeModelAdmin(SimpleHistoryAdmin):
    list_display = (
        "id",
        "name",
        "to_inbound_type_display",
    )
    search_fields = ("name", "to_inbound_type__name", "xray_outbound_template")
    list_filter = ("to_inbound_type",)
    inlines = (OutboundConnectorInline,)

    @admin.display(ordering="to_inbound_type")
    def to_inbound_type_display(self, obj):
        return obj.to_inbound_type and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.to_inbound_type),
            str(obj.to_inbound_type),
        )


class ConnectionTunnelOutboundInline(admin.StackedInline):
    extra = 0
    model = models.ConnectionTunnelOutbound
    autocomplete_fields = ("tunnel", "connector")
    ordering = ("created_at",)
    show_change_link = True
    template = "proxy_manager/admin/bar_stacked_inline.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("connector__outbound_type", "connector__inbound_spec", "connector__dest_node")
        )


class ConnectionRuleOutboundInline(admin.StackedInline):
    extra = 0
    model = models.ConnectionRuleOutbound
    form = forms.ConnectionRuleOutboundModelForm
    autocomplete_fields = "rule", "connector", "apply_node"
    ordering = ("created_at",)
    show_change_link = True
    template = "proxy_manager/admin/bar_stacked_inline.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "apply_node", "connector__outbound_type", "connector__inbound_spec", "connector__dest_node"
            )
        )


class ConnectionRuleInboundSpecInline(admin.TabularInline):
    extra = 0
    model = models.ConnectionRuleInboundSpec
    autocomplete_fields = ("spec", "connector")
    ordering = (
        "key",
        "created_at",
    )
    show_change_link = True

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("rule", "connector__inbound_spec", "connector__outbound_type", "connector__dest_node")
        )


@admin.register(models.OutboundConnector)
class OutboundConnectorModelAdmin(admin.ModelAdmin):
    list_display = ("id", "is_managed", "outbound_type_display", "inbound_spec_display", "dest_node_display")
    search_fields = (
        "outbound_type__name",
        "outbound_type__to_inbound_type__name",
        "outbound_type__xray_outbound_template",
    )
    list_filter = ("outbound_type__to_inbound_type",)
    autocomplete_fields = "outbound_type", "inbound_spec", "dest_node"
    inlines = (ConnectionRuleInboundSpecInline, ConnectionRuleOutboundInline, ConnectionTunnelOutboundInline)

    @admin.display(ordering="outbound_type")
    def outbound_type_display(self, obj):
        return obj.outbound_type and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.outbound_type),
            str(obj.outbound_type),
        )

    @admin.display(ordering="inbound_spec")
    def inbound_spec_display(self, obj):
        return obj.inbound_spec and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.inbound_spec),
            str(obj.inbound_spec),
        )

    @admin.display(ordering="dest_node")
    def dest_node_display(self, obj):
        return obj.dest_node and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.dest_node),
            str(obj.dest_node),
        )


@admin.register(models.ConnectionRuleOutbound)
class ConnectionRuleOutboundModelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "delay_display",
        "rule_display",
        "apply_node_display",
        "connector_display",
        "is_reverse",
        "balancer_allocation_str",
    )
    list_editable = ("balancer_allocation_str",)
    search_fields = (
        "connector__outbound_type__name",
        "connector__outbound_type__xray_outbound_template",
        "balancer_allocation_str",
    )
    list_filter = ("is_reverse", "connector__outbound_type__to_inbound_type", "rule")
    autocomplete_fields = ("rule", "connector", "apply_node")
    form = forms.ConnectionRuleOutboundModelForm
    change_form_template = "proxy_manager/admin/bar_change_form.html"

    def get_object(self, *args, **kwargs):
        obj = super().get_object(*args, **kwargs)
        if models.Config.get_solo().admin_panel_influx_delays:
            latest_delays = services.get_connection_outbound_latest_delays(
                _type=models.ConnectionRuleOutbound,
                ids=[obj.id],
            )
            obj.latest_delays = latest_delays.get(str(obj.id))
        return obj

    def get_changelist_instance(self, request):
        changelist_instance = super().get_changelist_instance(request)
        if models.Config.get_solo().admin_panel_influx_delays:
            latest_delays = services.get_connection_outbound_latest_delays(
                _type=models.ConnectionRuleOutbound, ids=[i.id for i in changelist_instance.result_list]
            )
            self.latest_delays = latest_delays
        else:
            # todo fix this fuck
            self.latest_delays = None
        return changelist_instance

    @admin.display()
    def delay_display(self, obj):
        if (latest_delays := getattr(self, "latest_delays", None)) is None:
            return "not active"
        r = latest_delays.get(str(obj.id), None)
        if r:
            return render_to_string("proxy_manager/admin/bars.html", context={"delay_list": r["delay_list"]})
        return None

    @admin.display(ordering="rule")
    def rule_display(self, obj):
        return obj.rule and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.rule),
            str(obj.rule),
        )

    @admin.display(ordering="connector")
    def connector_display(self, obj):
        return obj.connector and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.connector),
            str(obj.connector),
        )

    @admin.display(ordering="apply_node")
    def apply_node_display(self, obj):
        return obj.apply_node and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.apply_node),
            str(obj.apply_node),
        )


class ConnectionRuleBalancerInline(admin.StackedInline):
    extra = 0
    model = models.ConnectionRuleBalancer
    ordering = ("created_at",)


@admin.register(models.ConnectionRule)
class ConnectionRuleModelAdmin(SimpleHistoryAdmin):
    list_display = ("__str__", "periods_count_display", "alive_periods_count_display")
    inlines = (ConnectionRuleInboundSpecInline, ConnectionRuleBalancerInline, ConnectionRuleOutboundInline)
    search_fields = ("name", "xray_rules_template")

    def get_queryset(self, request):
        return super().get_queryset(request).ann_periods_count()

    def get_object(self, *args, **kwargs):
        obj = super().get_object(*args, **kwargs)
        if models.Config.get_solo().admin_panel_influx_delays:
            latest_delays = services.get_connection_outbound_latest_delays(
                _type=models.ConnectionRuleOutbound,
                ids=models.ConnectionRuleOutbound.objects.filter(rule=obj).values_list("id", flat=True),
            )
            self.latest_delays = latest_delays
        else:
            # todo fix this fuck
            self.latest_delays = None
        return obj

    @admin.display(ordering="periods_count")
    def periods_count_display(self, obj):
        return obj.periods_count

    @admin.display(ordering="alive_periods_count")
    def alive_periods_count_display(self, obj):
        return obj.alive_periods_count


@admin.register(models.InternalUser)
class InternalUserModelAdmin(admin.ModelAdmin):
    list_display = ("id", "node", "connection_rule", "is_active", "first_usage_at", "last_usage_at")
    list_filter = ("node",)
    search_fields = ("xray_uuid",)
    form = forms.InternalUserModelForm
    autocomplete_fields = ("node", "connection_rule")


class OutboundTypeInline(admin.StackedInline):
    extra = 0
    model = models.OutboundType
    ordering = ("created_at",)
    show_change_link = True


@admin.register(models.InboundType)
class InboundTypeModelAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ("__str__", "is_active", "is_template")
    search_fields = ("name", "inbound_template")
    inlines = (OutboundTypeInline,)


@admin.register(models.Balancer)
class BalancerModelAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ("__str__",)


@admin.register(models.ConnectionTunnelOutbound)
class ConnectionTunnelOutboundModelAdmin(admin.ModelAdmin):
    list_display = ("id", "delay_display", "tunnel_display", "connector_display", "is_reverse", "weight")
    autocomplete_fields = ("tunnel", "connector")
    change_form_template = "proxy_manager/admin/bar_change_form.html"

    def get_object(self, *args, **kwargs):
        obj = super().get_object(*args, **kwargs)
        if models.Config.get_solo().admin_panel_influx_delays:
            latest_delays = services.get_connection_outbound_latest_delays(
                _type=models.ConnectionTunnelOutbound,
                ids=[obj.id],
            )
            obj.latest_delays = latest_delays.get(str(obj.id))
        return obj

    def get_changelist_instance(self, request):
        changelist_instance = super().get_changelist_instance(request)
        if models.Config.get_solo().admin_panel_influx_delays:
            latest_delays = services.get_connection_outbound_latest_delays(
                _type=models.ConnectionTunnelOutbound, ids=[i.id for i in changelist_instance.result_list]
            )
            self.latest_delays = latest_delays
        else:
            # todo fix this fuck
            self.latest_delays = None
        return changelist_instance

    @admin.display()
    def delay_display(self, obj):
        if (latest_delays := getattr(self, "latest_delays", None)) is None:
            return "not active"
        r = latest_delays.get(str(obj.id), None)
        if r:
            return render_to_string("proxy_manager/admin/bars.html", context={"delay_list": r["delay_list"]})
        return None

    @admin.display(ordering="tunnel")
    def tunnel_display(self, obj):
        return obj.tunnel and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.tunnel),
            str(obj.tunnel),
        )

    @admin.display(ordering="connector")
    def connector_display(self, obj):
        return obj.connector and format_html(
            "<a href='{}'>{}</a>",
            admin_obj_change_url(obj.connector),
            str(obj.connector),
        )


class LocalTunnelPortInline(admin.StackedInline):
    extra = 0
    model = models.LocalTunnelPort
    autocomplete_fields = ("source_node",)
    ordering = ("created_at",)


@admin.register(models.ConnectionTunnel)
class ConnectionTunnelModelAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ("__str__", "source_node", "dest_node")
    search_fields = ("source_node__name", "dest_node__name")
    inlines = (
        LocalTunnelPortInline,
        ConnectionTunnelOutboundInline,
    )
    form = forms.ConnectionTunnelModelForm
    autocomplete_fields = ("source_node", "dest_node")

    def get_object(self, *args, **kwargs):
        obj = super().get_object(*args, **kwargs)
        if models.Config.get_solo().admin_panel_influx_delays:
            latest_delays = services.get_connection_outbound_latest_delays(
                _type=models.ConnectionTunnelOutbound,
                ids=models.ConnectionTunnelOutbound.objects.filter(tunnel=obj).values_list("id", flat=True),
            )
            self.latest_delays = latest_delays
        else:
            # todo fix this fuck
            self.latest_delays = None
        return obj


@admin.register(models.LocalTunnelPort)
class LocalTunnelPortModelAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ("__str__",)
    autocomplete_fields = ("source_node", "tunnel")


class InboundSpecOutboundConnectorInline(admin.StackedInline):
    model = models.OutboundConnector
    extra = 0
    autocomplete_fields = ("outbound_type",)
    ordering = ("created_at",)
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
    autocomplete_fields = ("domain_address", "ip_address", "domain_sni", "domainhost_header", "reality")
    inlines = (
        InboundSpecOutboundConnectorInline,
        ConnectionRuleInboundSpecInline,
    )

    @admin.display(ordering="inbound_type")
    def inbound_type_display(self, obj):
        return obj.inbound_type and format_html(
            "<a href='{}'>{}</a>",
            reverse("admin:proxy_manager_inboundtype_change", args=[obj.inbound_type.id]),
            str(obj.inbound_type),
        )


class InboundSpecInline(admin.StackedInline):
    model = models.InboundSpec
    extra = 0
    autocomplete_fields = ("domain_address", "ip_address", "domain_sni", "domainhost_header")
    ordering = ("created_at",)
    show_change_link = True


@admin.register(models.RealitySpec)
class RealitySpecModelAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ("__str__", "certificate_domain", "inbound_type", "for_ip", "port", "dest_ip")
    search_fields = (
        "certificate_domain__name",
        "for_ip__ip",
        "for_ip__ip__ip_nodepublicips__node__name",
        "dest_ip__ip",
        "description",
    )
    inlines = (InboundSpecInline,)
    autocomplete_fields = ("for_ip", "dest_ip", "certificate_domain")


# @admin.register(models.IPProxyUsageSpec)
# class IPProxyUsageSpecModelAdmin(admin.ModelAdmin):
#     list_display = ("__str__",)
#
#
# @admin.register(models.DomainProxyUsageSpec)
# class DomainProxyUsageSpecModelAdmin(admin.ModelAdmin):
#     list_display = ("__str__",)
