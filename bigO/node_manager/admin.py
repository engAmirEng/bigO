from django.contrib.humanize.templatetags.humanize import naturaltime
from django.db.models import Count
from rest_framework_api_key.admin import APIKeyModelAdmin
from decimal import Decimal, ROUND_HALF_DOWN

from bigO.node_manager import models
from django import forms
from django.contrib import admin


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


@admin.register(models.Node)
class NodeModelAdmin(admin.ModelAdmin):
    inlines = [NodePublicIPInline, NodeInnerProgramInline, NodeLatestSyncStatInline]
    list_display = ("__str__", "last_sync_req_display", "last_sync_duration_display", "sync_count_display")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("node_nodesyncstat")

    @admin.display(ordering="node_nodesyncstat__initiated_at")
    def last_sync_req_display(self, obj):
        nodesyncstat = getattr(obj, "node_nodesyncstat", None)
        if nodesyncstat is None:
            return "never"
        return naturaltime(nodesyncstat.initiated_at)
    @admin.display()
    def last_sync_duration_display(self, obj):
        nodesyncstat = getattr(obj, "node_nodesyncstat", None)
        if nodesyncstat is None:
            return "never"
        if nodesyncstat.respond_at is None:
            return "not responded"
        microseconds = (nodesyncstat.respond_at - nodesyncstat.initiated_at).microseconds
        return Decimal(microseconds / 1000000).quantize(Decimal("0.01"), rounding=ROUND_HALF_DOWN)

    @admin.display(ordering="node_nodesyncstat__count_up_to_now")
    def sync_count_display(self, obj):
        nodesyncstat = getattr(obj, "node_nodesyncstat", None)
        if nodesyncstat is None:
            return 0
        return nodesyncstat.count_up_to_now


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


class NodeCustomConfigTemplateInline(admin.StackedInline):
    extra = 1
    model = models.NodeCustomConfigTemplate


@admin.register(models.CustomConfigTemplate)
class CustomConfigTemplateModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "used_by_count")
    inlines = [NodeCustomConfigTemplateInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(used_by_count=Count("nodecustomconfigtemplates"))

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


class EasyTierNodeModelForm(forms.ModelForm):
    toml_config = forms.CharField(disabled=True, required=False, widget=forms.Textarea)

    class Meta:
        model = models.EasyTierNode
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["toml_config"].initial = self.instance.get_toml_config_content()
        else:
            self.fields["toml_config"].widget = forms.HiddenInput()


@admin.register(models.EasyTierNode)
class EasyTierNodeModelAdmin(admin.ModelAdmin):
    form = EasyTierNodeModelForm
    inlines = [EasyTierNodePeerInline, EasyTierNodeListenerInline]
    list_display = ("__str__", "network", "latency_first")
    list_editable = ("latency_first", )

    @admin.display()
    def toml_config_display(self, obj):
        return obj.get_toml_config_content()


class ProgramBinaryModelForm(forms.ModelForm):
    class Meta:
        model = models.ProgramBinary
        exclude = ["hash"]

    def clean(self):
        cleaned_data = super().clean()
        file = cleaned_data.get(models.ProgramBinary.file.field.name)
        if file:
            file_data = file.read()
            file_hash = models.ProgramBinary.get_hash(file_data)
            qs = models.ProgramBinary.objects.filter(hash=file_hash)
            if self.instance and self.instance.pk:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                self.add_error(models.ProgramBinary.file.field.name, f"file already exists, {file_hash}")
            else:
                cleaned_data["file_hash"] = file_hash

        return cleaned_data


@admin.register(models.ProgramBinary)
class ProgramBinaryModelAdmin(admin.ModelAdmin):
    form = ProgramBinaryModelForm
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
