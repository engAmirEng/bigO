from rest_framework_api_key.admin import APIKeyModelAdmin

from bigO.node_manager import models
from django.contrib import admin


@admin.register(models.Node)
class NodeModelAdmin(admin.ModelAdmin):
    pass


@admin.register(models.NodeAPIKey)
class NodeAPIKeyModelAdmin(APIKeyModelAdmin):
    pass


@admin.register(models.NginxConfigTemplate)
class NginxConfigTemplateModelAdmin(admin.ModelAdmin):
    pass
