import logging
import tomllib

from django.shortcuts import render
from django.template import Context, Template
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import models
from .permissions import HasNodeAPIKey

logger = logging.getLogger(__name__)


class ConfigSerializer(serializers.Serializer):
    id = serializers.CharField()
    raw_content = serializers.CharField()


class NodeBaseSyncAPIView(APIView):
    class OutputSerializer(serializers.Serializer):
        nginx_configs = ConfigSerializer(many=True, required=False)
        easytier_configs = ConfigSerializer(many=True, required=False)
        gost_configs = ConfigSerializer(many=True, required=False)

    permission_classes = [HasNodeAPIKey]

    def get_permissions(self):
        if getattr(self, "_permissions", None) is None:
            permissions = super().get_permissions()
            self._permissions = permissions
        return self._permissions

    def post(self, request):
        for i in self.get_permissions():
            if isinstance(i, HasNodeAPIKey) and i.had_permission:
                node_obj = i.api_key.node
                break
        else:
            raise NotImplementedError

        nginx_configs = []
        cct_qs = models.CustomConfigTemplate.objects.filter(nodecustomconfigtemplates__node=node_obj)
        for i in cct_qs:
            if i.type == models.CustomConfigTemplate.TypeChoices.NGINX:
                raw_content = Template(i.template).render(Context({"node_obj": node_obj}))
                nginx_configs.append({"id": f"custom_{i.id}", "raw_content": raw_content})
            else:
                logger.info(f"CustomConfigTemplate type {i.type} is not implemented.")

        easytier_configs = []
        etn_qs = models.EasyTierNode.objects.filter(node=node_obj)
        for i in etn_qs:
            raw_content = i.get_toml_config()
            try:
                tomllib.loads(raw_content)
            except tomllib.TOMLDecodeError as e:
                logger.critical(f"toml parsing {i} failed: {str(e)}")
                continue

            easytier_configs.append({"id": f"easytier_{i.id}", "raw_content": i.get_toml_config()})

        response_serializer = self.OutputSerializer(
            {"nginx_configs": nginx_configs, "easytier_configs": easytier_configs}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)
