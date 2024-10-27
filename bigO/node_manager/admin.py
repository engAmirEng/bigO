from rest_framework_api_key.admin import APIKeyModelAdmin

from bigO.node_manager import models
from django import forms
from django.contrib import admin


class NodePublicIPInline(admin.StackedInline):
    extra = 1
    model = models.NodePublicIP


@admin.register(models.Node)
class NodeModelAdmin(admin.ModelAdmin):
    inlines = [NodePublicIPInline]


@admin.register(models.NodeAPIKey)
class NodeAPIKeyModelAdmin(APIKeyModelAdmin):
    pass


@admin.register(models.PublicIP)
class PublicIPModelAdmin(admin.ModelAdmin):
    pass


@admin.register(models.CustomConfigTemplate)
class CustomConfigTemplateModelAdmin(admin.ModelAdmin):
    pass



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
            self.fields["toml_config"].initial = self.instance.get_toml_config()
        else:
            self.fields["toml_config"].widget = forms.HiddenInput()


@admin.register(models.EasyTierNode)
class EasyTierNodeModelAdmin(admin.ModelAdmin):
    form = EasyTierNodeModelForm
    inlines = [EasyTierNodePeerInline, EasyTierNodeListenerInline]

    @admin.display()
    def toml_config_display(self, obj):
        return obj.get_toml_config()
