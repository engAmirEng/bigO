from decimal import ROUND_HALF_DOWN, Decimal

import admin_extra_buttons.decorators
import admin_extra_buttons.mixins
from render_block import render_block_to_string
from rest_framework_api_key.admin import APIKeyModelAdmin

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.html import format_html

from . import forms, models


class NodeLatestSyncStatInline(admin.StackedInline):
    model = models.NodeLatestSyncStat


class NodePublicIPInline(admin.StackedInline):
    extra = 1
    model = models.NodePublicIP


class NodeInnerProgramInline(admin.StackedInline):
    extra = 1
    model = models.NodeInnerProgram


@admin.register(models.ContainerSpec)
class ContainerSpecModelAdmin(admin.ModelAdmin):
    pass


class NodeSupervisorConfigInline(admin.StackedInline):
    model = models.NodeSupervisorConfig


@admin.register(models.Node)
class NodeModelAdmin(admin_extra_buttons.mixins.ExtraButtonsMixin, admin.ModelAdmin):
    inlines = [NodePublicIPInline, NodeSupervisorConfigInline, NodeInnerProgramInline, NodeLatestSyncStatInline]
    list_display = (
        "__str__",
        "agent_spec_display",
        "last_sync_req_display",
        "last_sync_duration_display",
        "sync_count_display",
        "collect_metrics",
        "public_ips_display",
        "view_supervisor_page_display",
    )
    list_editable = ["collect_metrics"]

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


@admin.register(models.NodeAPIKey)
class NodeAPIKeyModelAdmin(APIKeyModelAdmin):
    pass


@admin.register(models.PublicIP)
class PublicIPModelAdmin(admin.ModelAdmin):
    pass


class ProgramVersionInline(admin.StackedInline):
    extra = 1
    model = models.ProgramVersion


@admin.register(models.Program)
class ProgramModelAdmin(admin.ModelAdmin):
    inlines = [ProgramVersionInline]


@admin.register(models.ProgramVersion)
class ProgramVersionModelAdmin(admin.ModelAdmin):
    pass


class NodeCustomConfigInline(admin.StackedInline):
    extra = 1
    model = models.NodeCustomConfig


class CustomConfigDependantFileInline(admin.StackedInline):
    extra = 1
    model = models.CustomConfigDependantFile


@admin.register(models.CustomConfig)
class CustomConfigModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "used_by_count")
    inlines = [CustomConfigDependantFileInline, NodeCustomConfigInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(used_by_count=Count("nodecustomconfigs"))

    @admin.display(ordering="used_by_count")
    def used_by_count(self, obj):
        return obj.used_by_count


@admin.register(models.EasyTierNetwork)
class EasyTierNetworkModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "ip_range")


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
    list_display = ("__str__", "network", "ipv4", "latency_first")
    list_editable = ("latency_first",)
    list_filter = ("network", "node")

    @admin.display()
    def toml_config_display(self, obj):
        return obj.get_toml_config_content()


@admin.register(models.ProgramBinary)
class ProgramBinaryModelAdmin(admin.ModelAdmin):
    form = forms.ProgramBinaryModelForm
    readonly_fields = ["hash"]

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
