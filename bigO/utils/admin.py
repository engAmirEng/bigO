from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from . import models


@admin.register(models.TextExtractor)
class TextExtractorModelAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    pass
