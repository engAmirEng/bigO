import uuid

from solo.admin import SingletonModelAdmin

from django import forms
from django.contrib import admin

from . import models


@admin.register(models.Config)
class ConfigModelAdmin(SingletonModelAdmin):
    list_display = ("__str__",)


@admin.register(models.Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("__str__",)


@admin.register(models.ISP)
class ISPAdmin(admin.ModelAdmin):
    list_display = ("__str__",)


class SubscriptionModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["xray_uuid"].initial = uuid.uuid4()
        self.fields["uuid"].initial = uuid.uuid4()

    class Meta:
        model = models.Subscription
        fields = "__all__"


@admin.register(models.Agency)
class AgencyModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)


@admin.register(models.Subscription)
class SubscriptionModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
    list_editable = []
    form = SubscriptionModelForm
    autocomplete_fields = ("user",)
    search_fields = ("user__name", "description")


@admin.register(models.OutboundGroup)
class OutboundGroupModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)


@admin.register(models.NodeOutbound)
class NodeOutboundModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)


@admin.register(models.ConnectionRule)
class ConnectionRuleModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)


@admin.register(models.Inbound)
class InboundModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
