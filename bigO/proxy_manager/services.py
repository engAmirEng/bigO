import django.template

from bigO.node_manager import models as node_manager_models
from . import models

async def get_sync_node(node: node_manager_models.Node) -> list:
    from xtlsapi import XrayClient, exception, utils
    proxy_manager_config = await models.Config.objects.aget()
    proxy_manager_config.nginx_config_template

    # language=json lines
    template = """
    {
        "inbounds": [
            {
                "tag": "h2-vless-grpc-new",
                "listen": "/opt/hiddify-config/xray/run/vlessg.sock,666",
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"id": "defaultuserguidsecret", "email": "defaultuserguidsecret@hiddify.com"}
                    ],
                  "decryption": "none"
                },
                "streamSettings": {
                    "network": "grpc",
                    "security": "none",
                    "grpcSettings": {
                        "serviceName": "PATH_VLESSPATH_GRPC"
                    }
                }
              }
        ]
    }
    """

    return


def get_proxy_manager_nginx_conf(node_obj) -> tuple[str, dict] | None:
    proxy_manager_config = models.Config.objects.get()
    context = django.template.Context({"node_obj": node_obj})
    template = "{% load node_manager %}" + proxy_manager_config.nginx_config_template
    result = django.template.Template(template).render(context=context)
    return result, context.get("deps", {"globals": []})
