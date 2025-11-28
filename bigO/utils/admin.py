from typing import overload

from django.db import models
from simple_history.admin import SimpleHistoryAdmin

from django.contrib import admin
from django.urls import reverse

from . import models as utils_models


@admin.register(utils_models.TextExtractor)
class TextExtractorModelAdmin(SimpleHistoryAdmin, admin.ModelAdmin):
    pass


@overload
def admin_obj_change_url(
    *,
    obj: models.Model,
    obj_id: None = ...,
    obj_type: None = ...
) -> str: ...      # or whatever the return type is


@overload
def admin_obj_change_url(
    *,
    obj: None = ...,
    obj_id: int,
    obj_type: type[models.Model],
) -> str: ...      # or whatever the return type is


def admin_obj_change_url(obj: models.Model|None=None, obj_id: int|None=None, obj_type: type[models.Model]|None=None):
    if obj:
        return reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=(obj.pk,))
    return reverse(f"admin:{obj_type._meta.app_label}_{obj_type._meta.model_name}_change", args=(obj_id,))
