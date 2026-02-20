from decimal import ROUND_HALF_DOWN, Decimal

import admin_extra_buttons.decorators
import admin_extra_buttons.mixins
import humanize.filesize
from django_json_widget.widgets import JSONEditorWidget
from render_block import render_block_to_string
from rest_framework_api_key.admin import APIKeyModelAdmin
from simple_history.admin import SimpleHistoryAdmin
from solo.admin import SingletonModelAdmin

from bigO.net_manager import models as net_manager_models
from bigO.proxy_manager import models as proxy_manager_models
from bigO.utils.admin import admin_obj_change_url
from config.celery_app import app as celery_app
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db.models import Count, JSONField, Q, QuerySet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext

from . import forms, models, services, tasks


@admin.register(models.Config)
class ConfigModelAdmin(
    SimpleHistoryAdmin,
    SingletonModelAdmin,
):
    list_display = ("__str__",)


class NodeLatestSyncStatInline(admin.StackedInline):
    model = models.NodeLatestSyncStat
    form = forms.NodeLatestSyncStatModelForm


class NodePublicIPInline(admin.TabularInline):
    extra = 1
    model = models.NodePublicIP
    autocomplete_fields = ("ip",)


class NodeInnerProgramInline(admin.TabularInline):
    extra = 1
    model = models.NodeInnerProgram
    autocomplete_fields = ("program_version",)


@admin.register(models.ContainerSpec)
class ContainerSpecModelAdmin(admin.ModelAdmin):
    pass


@admin.register(models.NetplanConfiguration)
class NetplanConfigurationModelAdmin(admin.ModelAdmin):
    search_fields = ("name",)


class NodeSupervisorConfigInline(admin.StackedInline):
    model = models.NodeSupervisorConfig


class O2SpecInline(admin.StackedInline):
    model = models.O2Spec
    autocomplete_fields = ("program",)


@admin.register(models.Node)
class NodeModelAdmin(admin_extra_buttons.mixins.ExtraButtonsMixin, admin.ModelAdmin):
    list_display = (
        "node_display",
        "last_sync_req_display",
        "downtime_attended",
        "public_ips_display",
        "agent_spec_display",
        "last_sync_duration_display",
        "collect_metrics",
        "collect_logs",
        "actions_display",
    )
    ordering = ("is_revoked", "-created_at")
    list_editable = ["downtime_attended", "collect_metrics", "collect_logs"]
    search_fields = ("name", "node_nodepublicips__ip__ip")
    actions = ["do_deploy"]
    inlines = [
        NodePublicIPInline,
        O2SpecInline,
        NodeSupervisorConfigInline,
        NodeInnerProgramInline,
        NodeLatestSyncStatInline,
    ]
    autocomplete_fields = ("netplan_config", "default_cert", "ansible_deploy_snippet", "ssh_public_keys")

    @admin.action(description="Do Deploy")
    def do_deploy(self, request, queryset: QuerySet[models.Node]):
        invalid_queryset = queryset.filter(
            Q(
                Q(ssh_port__isnull=True)
                | Q(ssh_user__isnull=True)
                | Q(ssh_user="")
                | Q(ssh_pass__isnull=True)
                | Q(ansible_deploy_snippet__isnull=True)
                | Q(ssh_pass="")
                | Q(o2spec__isnull=True)
            )
        )
        if invalid_record_count := invalid_queryset.count():
            self.message_user(
                request,
                gettext("cannot be done becuase of {0} records").format(invalid_record_count),
                messages.ERROR,
            )
            return
        for i in queryset:
            ansible_deploy_node = tasks.ansible_deploy_node if settings.DEBUG else tasks.ansible_deploy_node.delay
            ansible_deploy_node(node_id=i.id)
        self.message_user(
            request,
            gettext("started for {0} records").format(queryset.count()),
            messages.INFO,
        )

    @admin_extra_buttons.decorators.view(
        pattern="<int:node_pk>/basic_supervisor/",
        decorators=[login_required(login_url="admin:login")],
        permission="node_manager.add_node",
    )
    def basic_supervisor(self, request, node_pk: int):
        node_obj = get_object_or_404(models.Node, pk=node_pk)
        connect_form = forms.SupervisorRPCConnectTypeForm(request.GET or request.POST, node_obj=node_obj)
        url = connect_form.get_url()
        connect_form = admin.helpers.AdminForm(
            form=connect_form,
            fieldsets=[(None, {"fields": (tuple(connect_form.fields),)})],
            prepopulated_fields={},
            model_admin=self,
        )
        iframe_url = None
        link_url = None
        if url is not None:
            iframe_url, link_url = url

        context = self.get_common_context(request, title="Basic Supervisor")
        context["node_id"] = node_pk
        context["connect_form"] = connect_form
        context["iframe_url"] = iframe_url
        context["link_url"] = link_url
        if request.htmx:
            r = render_block_to_string(
                "node_manager/admin/basic_supervisor.html", block_name="content", context=context, request=request
            )
            return HttpResponse(r)
        return render(request, "node_manager/admin/basic_supervisor.html", context=context)

    def get_queryset(self, request):
        self.request = request
        qs = super().get_queryset(request)
        return qs.select_related("node_nodesyncstat", "supervisorconfig").ann_is_online().ann_generic_status()

    def annotate_cl(self):
        cl = getattr(self.request, "cl", None)
        if not cl:
            cl = self.get_changelist_instance(self.request)
            self.request.cl = cl

        ids = self.request.cl.result_list.values_list("id", flat=True)
        config = models.Config.get_solo()

        metrics = None
        if config.admin_show_node_metrics:
            try:
                metrics = self.request.cl.metrics
            except AttributeError:
                metrics = services.get_node_metrics(ids=ids)
        self.request.cl.metrics = metrics

    @admin.display(description="node display", ordering="is_revoked")
    def node_display(self, obj):
        return str(obj)

    @admin.display(description="public ips")
    def public_ips_display(self, obj):
        return ", ".join([i.mark + str(i.ip) for i in obj.node_nodepublicips.all()])

    @admin.display(ordering="node_nodesyncstat__initiated_at", description="last sync req")
    def last_sync_req_display(self, obj):
        nodesyncstat = getattr(obj, "node_nodesyncstat", None)
        match obj.generic_status:
            case models.GenericStatusChoices.ERROR:
                res = f"🔴 {naturaltime(nodesyncstat.initiated_at)}"
            case models.GenericStatusChoices.OFFLINE:
                res = f"⚫️ {naturaltime(nodesyncstat.initiated_at)}"
            case models.GenericStatusChoices.ATTENDED_OFFLINE:
                res = f"🔄 {naturaltime(nodesyncstat.initiated_at)}"
            case models.GenericStatusChoices.NEVER:
                res = "never"
            case models.GenericStatusChoices.ONLINE:
                res = f"🟢 {naturaltime(nodesyncstat.initiated_at)}"
            case _:
                raise NotImplementedError
        self.annotate_cl()
        if not self.request.cl.metrics:
            return res
        metric = self.request.cl.metrics.get(str(obj.id))
        if metric is None:
            res += f"<br>(?%)"
            return mark_safe(res)
        load_percent1 = Decimal(metric["load1"] / metric["n_cpus"] * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_DOWN
        )
        load_percent5 = Decimal(metric["load5"] / metric["n_cpus"] * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_DOWN
        )
        load_percent15 = Decimal(metric["load15"] / metric["n_cpus"] * 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_DOWN
        )
        mem_used_percent = Decimal(metric["mem_used_percent"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)
        res += f"<br>({load_percent1},{load_percent5},{load_percent15}|{mem_used_percent}%)"
        return mark_safe(res)

    @admin.display(ordering="node_nodesyncstat__agent_spec", description="agent spec")
    def agent_spec_display(self, obj):
        nodesyncstat = getattr(obj, "node_nodesyncstat", None)
        if nodesyncstat is None:
            return None
        return nodesyncstat.agent_spec

    @admin.display(description="last sync duration")
    def last_sync_duration_display(self, obj):
        nodesyncstat = getattr(obj, "node_nodesyncstat", None)
        if nodesyncstat is None:
            return "never"
        if nodesyncstat.respond_at is None:
            return "not responded"
        microseconds = (nodesyncstat.respond_at - nodesyncstat.initiated_at).microseconds
        return Decimal(microseconds / 1000000).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)

    @admin.display(description="Actions")
    def actions_display(self, obj):
        res = []
        supervisorconfig = getattr(obj, "supervisorconfig", None)
        if supervisorconfig and supervisorconfig.xml_rpc_api_expose_port:
            res.append(
                format_html(
                    # language=html
                    '<a href="{0}" target="_blank"><img src="{1}" style="height: 1.5rem"></a>',
                    reverse("admin:node_manager_node_basic_supervisor", kwargs={"node_pk": obj.id}),
                    static("images/supervisord.png"),
                )
            )
        if not res:
            return
        return mark_safe("".join(res))


@admin.register(models.NodePublicIP)
class NodePublicIPModelAdmin(admin.ModelAdmin):
    list_display = ("pk", "node", "ip")
    search_fields = ("node__name", "ip__ip")


class AnsibleTaskNodeInline(admin.StackedInline):
    model = models.AnsibleTaskNode
    extra = 0
    formfield_overrides = {
        JSONField: {"widget": JSONEditorWidget(mode="view")},
    }


@admin.register(models.AnsibleTask)
class AnsibleTaskModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "name", "status", "ok", "dark", "changed", "failures", "created_at", "finished_at")
    actions = ["revoke_with_terminate"]
    inlines = [AnsibleTaskNodeInline]
    formfield_overrides = {
        JSONField: {"widget": JSONEditorWidget(mode="view")},
    }

    def get_queryset(self, request):
        return super().get_queryset(request).ann_stats()

    @admin.action()
    def revoke_with_terminate(self, request, queryset: QuerySet[models.AnsibleTask]):
        celery_app.control.revoke([i.celery_task_id for i in queryset], terminate=True)
        self.message_user(
            request,
            gettext("terminated for {0} records").format(queryset.count()),
            messages.INFO,
        )


@admin.register(models.NodeAPIKey)
class NodeAPIKeyModelAdmin(APIKeyModelAdmin):
    autocomplete_fields = ("node",)


class RealitySpecForIPInline(admin.StackedInline):
    model = proxy_manager_models.RealitySpec
    extra = 0
    autocomplete_fields = ("dest_ip", "certificate_domain")
    fk_name = "for_ip"
    verbose_name = "ForIP RealitySpecs"
    show_change_link = True


class DNSRecordIPValueInline(admin.StackedInline):
    model = net_manager_models.DNSRecord
    extra = 0
    verbose_name = "IP Value DNS Record"
    autocomplete_fields = ("domain", "value_domain")
    show_change_link = True


@admin.register(models.PublicIP)
class PublicIPModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "node_display", "asn", "isp", "region")
    search_fields = ("name", "ip")
    inlines = (
        RealitySpecForIPInline,
        DNSRecordIPValueInline,
    )

    @admin.display(ordering="node_id", description="node")
    def node_display(self, obj):
        return obj.node_name


class ProgramVersionInline(admin.StackedInline):
    extra = 1
    model = models.ProgramVersion


@admin.register(models.Snippet)
class SnippetModelAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    search_fields = ("name", "template")


@admin.register(models.Program)
class ProgramModelAdmin(admin.ModelAdmin):
    inlines = [ProgramVersionInline]
    search_fields = ("name",)


@admin.register(models.ProgramVersion)
class ProgramVersionModelAdmin(admin.ModelAdmin):
    autocomplete_fields = ("program",)
    search_fields = ("program__name", "version")


@admin.register(models.SupervisorProcessInfo)
class SupervisorProcessInfoModelAdmin(admin.ModelAdmin):
    ordering = ("node", "name")
    list_display = (
        "id",
        "node",
        "name",
        "last_changed_at_display",
        "is_down_attended",
        "description",
        "statename_display",
        "last_captured_at_display",
    )
    list_filter = ("last_state", "name", "node")
    list_editable = ("is_down_attended",)
    search_fields = ("name",)
    autocomplete_fields = ("node",)

    @admin.display(ordering="last_statename", description="statename")
    def statename_display(self, obj: models.SupervisorProcessInfo):
        perv_fortime = obj.perv_captured_at - obj.perv_changed_at
        last_fortime = obj.last_captured_at - obj.last_changed_at
        perv_fortime_str = ""
        if perv_fortime:
            perv_fortime_str = str(perv_fortime)
        last_fortime_str = ""
        if last_fortime:
            last_fortime_str = str(last_fortime)
        return f"{obj.perv_statename}({perv_fortime_str}) -> {obj.last_statename}({last_fortime_str})"

    @admin.display(ordering="last_changed_at", description="last changed at")
    def last_changed_at_display(self, obj: models.SupervisorProcessInfo):
        return naturaltime(obj.last_changed_at)

    @admin.display(ordering="last_captured_at", description="last captured at")
    def last_captured_at_display(self, obj: models.SupervisorProcessInfo):
        return naturaltime(obj.last_captured_at)


class NodeCustomConfigInline(admin.StackedInline):
    extra = 1
    model = models.NodeCustomConfig
    autocomplete_fields = ("node",)


class CustomConfigDependantFileInline(admin.StackedInline):
    extra = 1
    model = models.CustomConfigDependantFile
    show_change_link = True
    autocomplete_fields = ("file",)


@admin.register(models.CustomConfig)
class CustomConfigModelAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    list_display = ("__str__", "used_by_count")
    list_filter = ("nodecustomconfigs__node",)
    search_fields = (
        "name",
        "program_version__program__name",
        "program_version__version",
        "run_opts_template",
        "dependantfiles__key",
        "dependantfiles__template",
        "dependantfiles__file__program__name",
        "dependantfiles__file__version",
    )
    inlines = [CustomConfigDependantFileInline, NodeCustomConfigInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(used_by_count=Count("nodecustomconfigs"))

    @admin.display(ordering="used_by_count")
    def used_by_count(self, obj):
        return obj.used_by_count


@admin.register(models.CustomConfigDependantFile)
class CustomConfigDependantFileModelAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    pass


@admin.register(models.EasyTierNetwork)
class EasyTierNetworkModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "program_version", "ip_range")
    list_select_related = ("program_version",)
    autocomplete_fields = ("program_version",)


@admin.register(models.EasyTierNodeListener)
class EasyTierNodeListenerModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "node__node", "node__network", "protocol", "port")
    list_select_related = ("node",)
    search_fields = ("node__node__name", "node__node__node_nodepublicips__ip__ip")


class EasyTierNodeListenerInline(admin.StackedInline):
    extra = 1
    model = models.EasyTierNodeListener


class EasyTierNodePeerInline(admin.StackedInline):
    extra = 1
    model = models.EasyTierNodePeer
    fk_name = models.EasyTierNodePeer.node.field.name
    autocomplete_fields = ("peer_listener", "peer_public_ip")


@admin.register(models.EasyTierNode)
class EasyTierNodeModelAdmin(admin.ModelAdmin):
    form = forms.EasyTierNodeModelForm
    inlines = [EasyTierNodePeerInline, EasyTierNodeListenerInline]
    list_display = ("__str__", "network_display", "preferred_program_version", "ipv4", "latency_first")
    list_editable = ("latency_first", "preferred_program_version")
    autocomplete_fields = ("preferred_program_version", "node")
    list_filter = ("network", "node")
    list_select_related = ("network",)

    @admin.display(ordering="network", description="Network")
    def network_display(self, obj):
        return obj.network or format_html(
            '<a href="{}">{}</a>', admin_obj_change_url(obj=obj.network), str(obj.network)
        )

    @admin.display()
    def toml_config_display(self, obj):
        return obj.get_toml_config_content()


@admin.register(models.ProgramBinary)
class ProgramBinaryModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "program_version__program__name", "program_version__version", "file_size_display")
    search_fields = ("hash", "program_version__program__name")
    form = forms.ProgramBinaryModelForm
    readonly_fields = ("hash",)
    autocomplete_fields = ("program_version",)

    @admin.display(description="file size")
    def file_size_display(self, obj: models.ProgramBinary):
        try:
            return humanize.filesize.naturalsize(obj.file.size)
        except FileNotFoundError as e:
            return str(e)

    def save_model(self, request, obj, form, change):
        if file_hash := form.cleaned_data.get("file_hash"):
            obj.hash = file_hash
        super().save_model(request, obj, form, change)


@admin.register(models.NodeInnerProgram)
class NodeInnerProgramModelAdmin(admin.ModelAdmin):
    pass


@admin.register(models.NodeLatestSyncStat)
class NodeLatestSyncStatModelAdmin(admin.ModelAdmin):
    pass
