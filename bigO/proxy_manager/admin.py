import uuid

from django import forms
from django.contrib import admin

from . import models


class SubscriptionModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["xray_uuid"].initial = uuid.uuid4()

    class Meta:
        model = models.Subscription
        fields = "__all__"


@admin.register(models.Subscription)
class SubscriptionModelAdmin(admin.ModelAdmin):
    list_display = ("__str__",)
    list_editable = []
    form = SubscriptionModelForm
    autocomplete_fields = ("user",)
    search_fields = ("user__name", "description")
