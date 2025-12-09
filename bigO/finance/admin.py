import polymorphic.admin

from django.contrib import admin

from . import forms, models


class InvoiceItemInline(polymorphic.admin.StackedPolymorphicInline):
    model = models.InvoiceItem

    @property
    def child_inlines(self):
        from bigO.proxy_manager.models import SubscriptionPlanInvoiceItem

        class SubscriptionPlanInvoiceItemInline(polymorphic.admin.StackedPolymorphicInline.Child):
            model = SubscriptionPlanInvoiceItem
            autocomplete_fields = (
                "created_by",
                "replacement",
                "apply_to",
                "issued_for",
                "issued_for",
                "delivered_period",
            )
            show_change_link = True

        return (SubscriptionPlanInvoiceItemInline,)


@admin.register(models.Invoice)
class InvoiceModelAdmin(polymorphic.admin.PolymorphicInlineSupportMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "total_price",
        "due_date",
        "status",
    )
    search_fields = ("uuid",)
    inlines = (InvoiceItemInline,)


@admin.register(models.InvoiceItem)
class InvoiceItemModelAdmin(polymorphic.admin.PolymorphicParentModelAdmin):
    list_display = (
        "id",
        "invoice",
        "total_price",
    )
    search_fields = ("invoice__uuid",)
    list_filter = (polymorphic.admin.PolymorphicChildModelFilter,)

    def get_child_models(self):
        from bigO.proxy_manager.models import SubscriptionPlanInvoiceItem

        return (SubscriptionPlanInvoiceItem,)


@admin.register(models.PaymentProvider)
class PaymentProviderModelAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)
    form = forms.PaymentProviderModelForm
    autocomplete_fields = ("admins",)


@admin.register(models.Payment)
class PaymentModelAdmin(admin.ModelAdmin):
    list_display = ("id", "uuid", "provider", "invoice", "amount")
    search_fields = ("uuid",)
