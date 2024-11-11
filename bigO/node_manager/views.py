import logging
import tomllib

from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, JsonResponse
from django.views import View
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import models, services
from .permissions import HasNodeAPIKey

logger = logging.getLogger(__name__)


class ProgramSerializer(serializers.Serializer):
    program_version_id = serializers.CharField(required=True)
    outer_binary_identifier = serializers.CharField(required=False)
    inner_binary_path = serializers.CharField(required=False)

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        if isinstance(instance, models.ProgramBinary):
            ret["outer_binary_identifier"] = instance.hash
        elif isinstance(instance, models.NodeInnerProgram):
            ret["inner_binary_path"] = instance.path
        return ret


class ConfigSerializer(serializers.Serializer):
    id = serializers.CharField()
    program = ProgramSerializer()
    run_opts = serializers.CharField(required=True)
    configfile_content = serializers.CharField(allow_null=True)
    config_file_ext = serializers.CharField(allow_null=True)
    hash = serializers.CharField()


class MetricSerializer(serializers.Serializer):
    ip_a = serializers.CharField()


class NodeBaseSyncAPIView(APIView):
    class InputSerializer(serializers.Serializer):
        metrics = MetricSerializer(required=False)

    class OutputSerializer(serializers.Serializer):
        configs = ConfigSerializer(many=True, required=False)

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

        input_ser = self.InputSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)
        input_data = input_ser.data
        services.node_spec_create(node=node_obj, ip_a=input_data["metrics"]["ip_a"])

        configs = []
        for i in node_obj.node_customconfigtemplates.all():
            program = i.get_program()
            if program is None:
                logger.critical(f"no program found for {i}")
                continue
            configs.append(
                ConfigSerializer(
                    {
                        "id": f"custom_{i.config_template.id}_{i.id}",
                        "program": ProgramSerializer(program).data,
                        "run_opts": i.get_run_opts(),
                        "configfile_content": i.get_config_content(),
                        "config_file_ext": i.config_template.config_file_ext,
                        "hash": i.get_hash(),
                    }
                ).data
            )

        etn_qs = models.EasyTierNode.objects.filter(node=node_obj)
        for i in etn_qs:
            configfile_content = i.get_toml_config_content()
            try:
                tomllib.loads(configfile_content)
            except tomllib.TOMLDecodeError as e:
                logger.critical(f"toml parsing {i} failed: {str(e)}")
                continue
            program = i.get_program()
            if program is None:
                logger.critical(f"no program found for {i}")
                continue

            configs.append(
                ConfigSerializer(
                    {
                        "id": f"eati_{i.id}",
                        "program": ProgramSerializer(program).data,
                        "run_opts": i.get_run_opts(),
                        "configfile_content": i.get_toml_config_content(),
                        "config_file_ext": None,
                        "hash": i.get_hash(),
                    }
                ).data
            )

        return Response(self.OutputSerializer({"configs": configs}).data, status=status.HTTP_200_OK)


class NodeProgramBinaryContentByHashAPIView(UserPassesTestMixin, View):
    def test_func(self):
        perm = HasNodeAPIKey()
        has_perm = perm.has_permission(request=self.request, view=None)
        if not has_perm:
            return False
        self.node = perm.api_key.node
        return True

    def handle_no_permission(self):
        raise PermissionDenied("which node are you?")

    def get(self, request, hash: str):
        obj = models.ProgramBinary.objects.filter(hash=hash).first()
        if obj is None:
            return JsonResponse({}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(obj.file)
