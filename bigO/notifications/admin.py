from django.contrib import admin

from . import forms, models


@admin.register(models.ForeignTemplate)
class ForeignTemplateAdmin(admin.ModelAdmin):
    form = forms.ForeignTemplateForm


class ForeignTemplateInline(admin.TabularInline):
    model = models.ForeignTemplate
    form = forms.ForeignTemplateForm
    extra = 0


@admin.register(models.NotificationAccount)
class NotificationAccountModelAdmin(admin.ModelAdmin):
    list_display = ("__str__", "provider", "type", "cost_ratio")
    inlines = [ForeignTemplateInline]
    form = forms.NotificationAccountModelForm


class NotifiedMessageContextTabularInline(admin.TabularInline):
    model = models.NotifiedMessageContext
    extra = 1


@admin.register(models.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "id",
        "created_at",
        "notification_account",
        "to",
        "base_cost",
        "final_cost",
    )
    search_fields = ("to_user__username",)
    list_filter = (
        "notifiedmessagecontexts__message_context__key",
        "notification_account",
        "notification_account__type",
        "notification_account__provider",
    )
    autocomplete_fields = ("to_user",)
    inlines = (NotifiedMessageContextTabularInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("notification_account", "to_user")

    def to(self, instance):
        return instance.to_user or instance.to_customer


@admin.register(models.MessageContext)
class MessageContextAdmin(admin.ModelAdmin):
    list_display = ("__str__", "key", "value")
    form = forms.MessageContextForm
