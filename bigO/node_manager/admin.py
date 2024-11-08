from rest_framework_api_key.admin import APIKeyModelAdmin

from bigO.node_manager import models
from django import forms
from django.contrib import admin


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
    inlines = [NodePublicIPInline, NodeInnerProgramInline]


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
    inlines = [NodeCustomConfigTemplateInline]


@admin.register(models.EasyTierNetwork)
class EasyTierNetworkModelAdmin(admin.ModelAdmin):
    pass


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
            file_hash = models.ProgramBinary.gen_hash(file_data)
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
