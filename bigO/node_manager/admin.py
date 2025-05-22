from decimal import ROUND_HALF_DOWN, Decimal

import admin_extra_buttons.decorators
import admin_extra_buttons.mixins
import humanize.filesize
from django_json_widget.widgets import JSONEditorWidget
from render_block import render_block_to_string
from rest_framework_api_key.admin import APIKeyModelAdmin

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db.models import Count, JSONField, Q, QuerySet
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext

from . import forms, models, tasks


class NodeLatestSyncStatInline(admin.StackedInline):
    model = models.NodeLatestSyncStat


class NodePublicIPInline(admin.StackedInline):
    extra = 1
    model = models.NodePublicIP


class NodeInnerProgramInline(admin.StackedInline):
    extra = 1
    model = models.NodeInnerProgram
    autocomplete_fields = ("program_version",)


@admin.register(models.ContainerSpec)
class ContainerSpecModelAdmin(admin.ModelAdmin):
    pass


class NodeSupervisorConfigInline(admin.StackedInline):
    model = models.NodeSupervisorConfig


class O2SpecInline(admin.StackedInline):
    model = models.O2Spec
    autocomplete_fields = ("program", "ansible_deploy_snippet")


@admin.register(models.Node)
class NodeModelAdmin(admin_extra_buttons.mixins.ExtraButtonsMixin, admin.ModelAdmin):
    list_display = (
        "__str__",
        "agent_spec_display",
        "last_sync_req_display",
        "last_sync_duration_display",
        "sync_count_display",
        "collect_metrics",
        "collect_logs",
        "public_ips_display",
        "view_supervisor_page_display",
    )
    list_editable = ["collect_metrics", "collect_logs"]
    search_fields = ("name",)
    actions = ["do_deploy"]
    inlines = [
        NodePublicIPInline,
        O2SpecInline,
        NodeSupervisorConfigInline,
        NodeInnerProgramInline,
        NodeLatestSyncStatInline,
    ]

    @admin.action(description="Do Deploy")
    def do_deploy(self, request, queryset: QuerySet[models.Node]):
        invalid_queryset = queryset.filter(
            Q(
                Q(ssh_port__isnull=True)
                | Q(ssh_user__isnull=True)
                | Q(ssh_user="")
                | Q(ssh_pass__isnull=True)
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
        qs = super().get_queryset(request)
        return qs.select_related("node_nodesyncstat", "supervisorconfig")

    @admin.display(description="public ips")
    def public_ips_display(self, obj):
        return ", ".join([str(i.ip) for i in obj.node_nodepublicips.all()])

    @admin.display(ordering="node_nodesyncstat__initiated_at", description="last sync req")
    def last_sync_req_display(self, obj):
        nodesyncstat = getattr(obj, "node_nodesyncstat", None)
        if nodesyncstat is None:
            return "never"
        return naturaltime(nodesyncstat.initiated_at)

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

    @admin.display(ordering="node_nodesyncstat__count_up_to_now", description="sync count")
    def sync_count_display(self, obj):
        nodesyncstat = getattr(obj, "node_nodesyncstat", None)
        if nodesyncstat is None:
            return 0
        return nodesyncstat.count_up_to_now

    @admin.display(description="view supervisor page")
    def view_supervisor_page_display(self, obj):
        supervisorconfig = getattr(obj, "supervisorconfig", None)
        if supervisorconfig is None or not supervisorconfig.xml_rpc_api_expose_port:
            return None
        return format_html(
            '<a href="{}" target="_blank">View Supervisor</a>',
            reverse("admin:node_manager_node_basic_supervisor", kwargs={"node_pk": obj.id}),
        )


class AnsibleTaskNodeInline(admin.StackedInline):
    model = models.AnsibleTaskNode
    extra = 0
    formfield_overrides = {
        JSONField: {"widget": JSONEditorWidget},
    }


@admin.register(models.AnsibleTask)
class AnsibleTaskModelAdmin(admin.ModelAdmin):
    inlines = [AnsibleTaskNodeInline]
    list_display = ("__str__", "name", "status", "ok", "dark", "changed", "failures", "created_at", "finished_at")

    formfield_overrides = {
        JSONField: {"widget": JSONEditorWidget},
    }

    def get_queryset(self, request):
        return super().get_queryset(request).ann_stats()


@admin.register(models.NodeAPIKey)
class NodeAPIKeyModelAdmin(APIKeyModelAdmin):
    pass


@admin.register(models.PublicIP)
class PublicIPModelAdmin(admin.ModelAdmin):
    search_fields = ("name", "ip")


class ProgramVersionInline(admin.StackedInline):
    extra = 1
    model = models.ProgramVersion


@admin.register(models.Snippet)
class SnippetModelAdmin(admin.ModelAdmin):
    search_fields = ("name", "template")


@admin.register(models.Program)
class ProgramModelAdmin(admin.ModelAdmin):
    inlines = [ProgramVersionInline]
    search_fields = ("name",)


@admin.register(models.ProgramVersion)
class ProgramVersionModelAdmin(admin.ModelAdmin):
    autocomplete_fields = ("program",)
    search_fields = ("program__name", "version")


class NodeCustomConfigInline(admin.StackedInline):
    extra = 1
    model = models.NodeCustomConfig


class CustomConfigDependantFileInline(admin.StackedInline):
    extra = 1
    model = models.CustomConfigDependantFile


@admin.register(models.CustomConfig)
class CustomConfigModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "used_by_count")
    list_filter = ("nodecustomconfigs__node",)
    inlines = [CustomConfigDependantFileInline, NodeCustomConfigInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(used_by_count=Count("nodecustomconfigs"))

    @admin.display(ordering="used_by_count")
    def used_by_count(self, obj):
        return obj.used_by_count


@admin.register(models.EasyTierNetwork)
class EasyTierNetworkModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "program_version", "ip_range")
    list_select_related = ("program_version",)


class EasyTierNodeListenerInline(admin.StackedInline):
    extra = 1
    model = models.EasyTierNodeListener


class EasyTierNodePeerInline(admin.StackedInline):
    extra = 1
    model = models.EasyTierNodePeer
    fk_name = models.EasyTierNodePeer.node.field.name


@admin.register(models.EasyTierNode)
class EasyTierNodeModelAdmin(admin.ModelAdmin):
    form = forms.EasyTierNodeModelForm
    inlines = [EasyTierNodePeerInline, EasyTierNodeListenerInline]
    list_display = ("__str__", "network_display", "preferred_program_version", "ipv4", "latency_first")
    list_editable = ("latency_first", "preferred_program_version")
    autocomplete_fields = ("preferred_program_version",)
    list_filter = ("network", "node")
    list_select_related = ("network",)

    @admin.display(ordering="network", description="Network")
    def network_display(self, obj):
        url = reverse(
            f"admin:{obj.network._meta.app_label}_{obj.network._meta.model_name}_change", args=(obj.network.pk,)
        )
        return format_html('<a href="{}">{}</a>', url, str(obj.network))

    @admin.display()
    def toml_config_display(self, obj):
        return obj.get_toml_config_content()


@admin.register(models.ProgramBinary)
class ProgramBinaryModelAdmin(admin.ModelAdmin):
    form = forms.ProgramBinaryModelForm
    readonly_fields = ["hash"]
    autocomplete_fields = ("program_version",)
    list_display = ("__str__", "file_size_display")
    search_fields = ("hash", "program_version__program__name")

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
