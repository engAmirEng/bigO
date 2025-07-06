from django.contrib import admin
from django.db.models import Prefetch
from solo.admin import SingletonModelAdmin

from . import models

@admin.register(models.Config)
class ConfigModelAdmin(SingletonModelAdmin):
    pass


@admin.register(models.Ahrom)
class AhromModelAdmin(admin.ModelAdmin):
    list_display = ("contract_num", "strike_price")
    search_fields = ("contract_num", )


@admin.register(models.Type1Config)
class Type1ConfigModelAdmin(admin.ModelAdmin):
    list_display = ("ahrom", "order")
    ordering = ("order",)
    search_fields = ("ahrom__contract_num", )
    autocomplete_fields = ("ahrom", )


class Type2RelateInline(admin.StackedInline):
    extra = 1
    model = models.Type2Relate
    autocomplete_fields = ("kharid_ahrom",)
    ordering = ("order",)


@admin.register(models.Type2Config)
class Type2ConfigModelAdmin(admin.ModelAdmin):
    list_display = ("foroosh_ahrom", "order", "related_kharids")
    ordering = ("order",)
    search_fields = ("foroosh_ahrom__contract_num", "relates__kharid_ahrom__contract_num")
    inlines = (Type2RelateInline, )
    autocomplete_fields = ("foroosh_ahrom", )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            Prefetch("relates", queryset=models.Type2Relate.objects.order_by("order"), to_attr="all_relates"))

    @admin.display()
    def related_kharids(self, obj):
        return ", ".join([i.kharid_ahrom.contract_num for i in obj.all_relates])
