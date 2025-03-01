import django.template

from bigO.node_manager import models as node_manager_models
from . import models

def get_sync_node(node: node_manager_models.Node) -> list:
    from xtlsapi import XrayClient, exception, utils

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


def get_proxy_manager_nginx_conf(node_obj) -> tuple[str, str, dict]:
    proxy_manager_config = models.Config.objects.get()
    context = django.template.Context({"node_obj": node_obj})
    nginx_config_http_template = "{% load node_manager %}" + proxy_manager_config.nginx_config_http_template
    nginx_config_http_result = django.template.Template(nginx_config_http_template).render(context=context)
    nginx_config_stream_template = "{% load node_manager %}" + proxy_manager_config.nginx_config_stream_template
    nginx_config_stream_result = django.template.Template(nginx_config_stream_template).render(context=context)
    return nginx_config_http_result, nginx_config_stream_result, context.get("deps", {"globals": []})


def get_xray_conf(node_obj) -> tuple[str, str, dict]:
    proxy_manager_config = models.Config.objects.get()
    context = django.template.Context({"node": node_obj})
    xray_config_template = "{% load node_manager proxy_manager %}" + proxy_manager_config.xray_config_template
    result = django.template.Template(xray_config_template).render(context=context)
    run_opt = django.template.Template("-c *#path:main#*").render(context=context)
    return run_opt, result, context.get("deps", {"globals": []})
