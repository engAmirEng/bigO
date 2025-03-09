import logging
import socket
import ssl
import tomllib
from hashlib import sha256
from urllib.parse import urlparse

import aiohttp.client_exceptions
import pydantic
import sentry_sdk
from asgiref.sync import sync_to_async

import bigO.utils.exceptions
from bigO.core import models as core_models
from bigO.proxy_manager import services as proxy_manager_services
from bigO.utils.decorators import xframe_options_sameorigin
from django.contrib.auth.mixins import UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import models, services, typing
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


class ConfigDependantFileSerializer(serializers.Serializer):
    key = serializers.SlugField()
    content = serializers.CharField()
    extension = serializers.CharField(allow_null=True)
    hash = serializers.SerializerMethodField()

    def get_hash(self, obj):
        content = self.fields["content"].get_attribute(obj)
        extension = self.fields["extension"].get_attribute(obj)
        return sha256((content + str(extension)).encode("utf-8")).hexdigest()


class ConfigSerializer(serializers.Serializer):
    id = serializers.CharField()
    program = ProgramSerializer()
    run_opts = serializers.CharField(required=True)
    new_run_opts = serializers.CharField(required=True)
    comma_separated_environment = serializers.CharField(required=False)
    configfile_content = serializers.CharField(allow_null=True)
    config_file_ext = serializers.CharField(allow_null=True)
    hash = serializers.CharField()
    dependant_files = ConfigDependantFileSerializer(many=True)


class NodeBaseSyncAPIView(APIView):
    class InputSchema(pydantic.BaseModel):
        metrics: typing.MetricSchema
        configs_states: list[typing.ConfigStateSchema] | None = None
        smallo1_logs: typing.SupervisorProcessTailLogSerializerSchema | None = None

    class OutputSerializer(serializers.Serializer):
        configs = ConfigSerializer(many=True, required=False)
        global_deps = ConfigDependantFileSerializer(many=True)

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
        node_sync_stat_obj = services.create_node_sync_stat(request=request, node=node_obj)

        try:
            input_data = self.InputSchema(**request.data)
        except pydantic.ValidationError as e:
            sentry_sdk.capture_exception(e)
            raise bigO.utils.exceptions.pydantic_to_drf_error(e)
        services.node_process_stats(
            node_obj=node_obj, configs_states=input_data.configs_states, smallo1_logs=input_data.smallo1_logs
        )
        services.node_spec_create(node=node_obj, ip_a=input_data.metrics.ip_a)

        site_config: core_models.SiteConfiguration = core_models.SiteConfiguration.objects.get()

        global_deps = []
        default_cert = node_obj.get_default_cert()
        global_deps.extend(
            [
                {"key": "default_cert", "content": default_cert.content, "extension": None},
                {"key": "default_cert_key", "content": default_cert.private_key.content, "extension": None},
            ]
        )
        if site_config.htpasswd_content:
            global_deps.append(
                {"key": "default_basic_http_file", "content": site_config.htpasswd_content, "extension": None}
            )

        configs = []
        for i in node_obj.node_customconfigs.all():
            program = i.get_program()
            if program is None:
                logger.critical(f"no program found for {i}")
                continue
            config_depandant_content = i.get_config_depandant_content()
            run_opts = i.get_run_opts()
            if len(config_depandant_content) == 1:
                new_run_opts = run_opts.replace("CONFIGFILEPATH", f"*#path:{config_depandant_content[0]['key']}#*")
            else:
                new_run_opts = run_opts
            configs.append(
                ConfigSerializer(
                    {
                        "id": f"custom_{i.custom_config.id}_{i.id}",
                        "program": ProgramSerializer(program).data,
                        "run_opts": run_opts,
                        "new_run_opts": new_run_opts,
                        "configfile_content": config_depandant_content[0]["content"]
                        if config_depandant_content
                        else None,
                        "config_file_ext": config_depandant_content[0]["extension"]
                        if config_depandant_content
                        else None,
                        "hash": i.get_hash(),
                        "dependant_files": ConfigDependantFileSerializer(
                            [
                                {"key": i["key"], "content": i["content"], "extension": i["extension"]}
                                for i in config_depandant_content
                            ],
                            many=True,
                        ).data,
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
            toml_config_content = i.get_toml_config_content()
            run_opts = i.get_run_opts()
            new_run_opts = run_opts.replace("CONFIGFILEPATH", "*#path:main#*")
            configs.append(
                ConfigSerializer(
                    {
                        "id": f"eati_{i.id}",
                        "program": ProgramSerializer(program).data,
                        "run_opts": run_opts,
                        "new_run_opts": new_run_opts,
                        "configfile_content": toml_config_content,
                        "config_file_ext": None,
                        "hash": i.get_hash(),
                        "dependant_files": ConfigDependantFileSerializer(
                            [{"key": "main", "content": toml_config_content, "extension": None}], many=True
                        ).data,
                    }
                ).data
            )

        telegraf_conf = services.get_telegraf_conf(node=node_obj)
        telegraf_program = (
            site_config.main_telegraf.get_program_for_node(node_obj) if site_config.main_telegraf else None
        )
        if telegraf_conf:
            if telegraf_program is None:
                logger.critical("no program found for telegraf_conf")
            else:
                influential_global_deps = [
                    i["content"] for i in global_deps if i["key"] in telegraf_conf[2]["globals"]
                ]
                global_telegraf_conf_hash = sha256(
                    (telegraf_conf[0] + telegraf_conf[1] + "".join(influential_global_deps)).encode("utf-8")
                ).hexdigest()
                configs.append(
                    ConfigSerializer(
                        {
                            "id": "telegraf_conf",
                            "program": telegraf_program,
                            "run_opts": telegraf_conf[0],
                            "new_run_opts": telegraf_conf[0],
                            "configfile_content": telegraf_conf[1],
                            "config_file_ext": None,
                            "hash": global_telegraf_conf_hash,
                            "dependant_files": ConfigDependantFileSerializer(
                                [{"key": "main", "content": telegraf_conf[1], "extension": None}], many=True
                            ).data,
                        }
                    ).data
                )

        xray_conf = proxy_manager_services.get_xray_conf(node_obj=node_obj)
        xray_program = site_config.main_xray.get_program_for_node(node_obj)
        if xray_conf:
            if xray_program is None:
                logger.critical("no program found for xray_conf")
            else:
                influential_global_deps = [i["content"] for i in global_deps if i["key"] in xray_conf[2]["globals"]]
                xray_conf_hash = sha256(
                    (xray_conf[0] + xray_conf[1] + "".join(influential_global_deps)).encode("utf-8")
                ).hexdigest()
                configs.append(
                    ConfigSerializer(
                        {
                            "id": "xray_conf",
                            "program": xray_program,
                            "run_opts": xray_conf[0],
                            "new_run_opts": xray_conf[0],
                            "configfile_content": xray_conf[1],
                            "config_file_ext": ".json",
                            "hash": xray_conf_hash,
                            "dependant_files": ConfigDependantFileSerializer(
                                [{"key": "main", "content": xray_conf[1], "extension": ".json"}], many=True
                            ).data,
                        }
                    ).data
                )

        global_haproxy_conf = services.get_global_haproxy_conf(node=node_obj)
        haproxy_program = site_config.main_haproxy.get_program_for_node(node_obj)
        if global_haproxy_conf:
            if haproxy_program is None:
                logger.critical("no program found for global_haproxy_conf")
            else:
                influential_global_deps = [
                    i["content"] for i in global_deps if i["key"] in global_haproxy_conf[2]["globals"]
                ]
                global_haproxy_conf_hash = sha256(
                    (global_haproxy_conf[0] + global_haproxy_conf[1] + "".join(influential_global_deps)).encode(
                        "utf-8"
                    )
                ).hexdigest()
                configs.append(
                    ConfigSerializer(
                        {
                            "id": "global_haproxy_conf",
                            "program": haproxy_program,
                            "run_opts": global_haproxy_conf[0],
                            "new_run_opts": global_haproxy_conf[0],
                            "configfile_content": global_haproxy_conf[1],
                            "config_file_ext": None,
                            "hash": global_haproxy_conf_hash,
                            "dependant_files": ConfigDependantFileSerializer(
                                [{"key": "main", "content": global_haproxy_conf[1], "extension": None}], many=True
                            ).data,
                        }
                    ).data
                )

        global_nginx_conf = services.get_global_nginx_conf(node=node_obj)
        nginx_program = site_config.main_nginx.get_program_for_node(node_obj)
        if global_nginx_conf:
            if nginx_program is None:
                logger.critical("no program found for global_nginx_conf")
            else:
                influential_global_deps = [
                    i["content"] for i in global_deps if i["key"] in global_nginx_conf[2]["globals"]
                ]
                global_nginx_conf_hash = sha256(
                    (global_nginx_conf[0] + global_nginx_conf[1] + "".join(influential_global_deps)).encode("utf-8")
                ).hexdigest()
                configs.append(
                    ConfigSerializer(
                        {
                            "id": "global_nginx_conf",
                            "program": nginx_program,
                            "run_opts": global_nginx_conf[0],
                            "new_run_opts": global_nginx_conf[0],
                            "configfile_content": global_nginx_conf[1],
                            "config_file_ext": None,
                            "hash": global_nginx_conf_hash,
                            "dependant_files": ConfigDependantFileSerializer(
                                [{"key": "main", "content": global_nginx_conf[1], "extension": None}], many=True
                            ).data,
                        }
                    ).data
                )

        response_payload = self.OutputSerializer({"configs": configs, "global_deps": global_deps}).data
        services.complete_node_sync_stat(obj=node_sync_stat_obj, response_payload=response_payload)
        return Response(response_payload, status=status.HTTP_200_OK)


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


class CustomResolver(aiohttp.DefaultResolver):
    def __init__(self, custom_ip):
        super().__init__()
        self.custom_ip = custom_ip

    async def resolve(self, host, port=0, family=socket.AF_INET):
        return [
            {
                "hostname": host,
                "host": self.custom_ip,
                "port": port,
                "family": family,
                "proto": 0,
                "flags": 0,
            }
        ]


@xframe_options_sameorigin
async def node_supervisor_server_proxy_view(request, node_id: int, way: str, path: str = ""):
    is_superuser = await sync_to_async(lambda: request.user.is_superuser)()
    if not is_superuser:
        raise PermissionDenied
    node_obj = await sync_to_async(get_object_or_404)(
        models.Node.objects.select_related("supervisorconfig"), id=node_id
    )
    if (
        supervisorconfig_obj := getattr(node_obj, "supervisorconfig", None)
    ) is None or not supervisorconfig_obj.xml_rpc_api_expose_port:
        return HttpResponse("xml_rpc_api_expose_port is not active for this node")

    try:
        method, *other = way.split(":")
    except:
        return HttpResponse(status=400)
    if method == "public_ip":
        public_ip = await models.PublicIP.objects.filter(ip_nodepublicips__node=node_obj, id=other[0]).afirst()
        if public_ip is None:
            return HttpResponse("mathching public ip not found")
        ip = public_ip.ip.ip
    elif method == "easytier":
        easytiernode = await models.EasyTierNode.objects.filter(node=node_obj, network_id=other[0]).afirst()
        if easytiernode is None:
            return HttpResponse("mathching easytier node not found")
        ip = easytiernode.ipv4.ip
    else:
        return HttpResponse(status=400)

    host_name = f"supervisor.{node_obj.name}.com"
    url = f"https://{host_name}:{supervisorconfig_obj.xml_rpc_api_expose_port}/" + path
    config: core_models.SiteConfiguration = await core_models.SiteConfiguration.objects.select_related(
        "nodes_ca_cert"
    ).aget()
    basicauth = aiohttp.BasicAuth(login=config.basic_username, password=config.basic_password)
    resolver = CustomResolver(custom_ip=str(ip))
    connector = aiohttp.TCPConnector(resolver=resolver)
    session = aiohttp.ClientSession(headers={"Host": host_name}, connector=connector, auth=basicauth)
    client = await session.__aenter__()
    sslcontext = ssl.create_default_context(cadata=config.nodes_ca_cert.content)
    try:
        response = await client.request(
            ssl=sslcontext, method=request.method, url=url, params=request.GET, allow_redirects=False
        )
    except Exception as e:
        return HttpResponse(str(e), status=500)
    if 300 <= response.status < 400:
        location = urlparse(response.headers["Location"])
        await response.release()
        await session.__aexit__(None, None, None)
        if location.path == "/":
            return redirect(
                reverse("node_manager:node_supervisor_server_proxy_root_view", kwargs={"node_id": node_id, "way": way})
                + f"?{location.query}"
            )
        else:
            return redirect(
                reverse(
                    "node_manager:node_supervisor_server_proxy_view",
                    kwargs={"node_id": node_id, "path": location.path},
                )
                + f"?{location.query}"
            )
    return StreamingHttpResponse(
        streaming_response(session=session, response=response),
        content_type=response.content_type,
        status=response.status,
    )


async def streaming_response(session: aiohttp.ClientSession, response: aiohttp.ClientResponse):
    try:
        async for chunk in response.content.iter_any():
            yield chunk
    finally:
        await response.release()
        await session.__aexit__(None, None, None)
