from django.contrib import admin, messages

from . import models


@admin.register(models.Panel)
class PanelModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "agency", "bot", "is_active", "member_subscription_notif")
    list_editable = ("member_subscription_notif",)
