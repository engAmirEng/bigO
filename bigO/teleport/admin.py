from django.contrib import admin, messages

from . import models


@admin.register(models.Panel)
class RegionModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "agency", "bot", "is_active")
