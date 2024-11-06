from django.contrib import admin

from . import models


@admin.register(models.TextExtractor)
class TextExtractorModelAdmin(admin.ModelAdmin):
    pass
