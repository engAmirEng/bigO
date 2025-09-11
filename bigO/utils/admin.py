from simple_history.admin import SimpleHistoryAdmin

from django.contrib import admin
from django.urls import reverse

from . import models


@admin.register(models.TextExtractor)
class TextExtractorModelAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    pass


def admin_obj_change_url(obj):
    return reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=(obj.pk,))
