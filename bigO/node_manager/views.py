from bigO.node_manager.permissions import HasNodeAPIKey
from bigO.node_manager.serializer import NodeInfoSerializer
from django.template import Context, Template
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView


class NodeSyncMeAPIView(APIView):
    class InputSerializer(serializers.Serializer):
        info = NodeInfoSerializer()

    class OutputSerializer(serializers.Serializer):
        nginx_config = serializers.CharField()

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

        if node_obj.nginx_config_template:
            nginx_config = Template(node_obj.nginx_config_template.template).render(Context({"node_obj": node_obj}))
        else:
            nginx_config = None

        response_serializer = self.OutputSerializer({"nginx_config": nginx_config})
        return Response(response_serializer.data, status=status.HTTP_200_OK)
