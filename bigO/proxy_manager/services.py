from collections import defaultdict

import django.template
from bigO.node_manager import models as node_manager_models
from django.db.models import Q
from django.utils import timezone

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


def get_xray_outbounds(node_obj):
    res = []
    balancers = defaultdict(list)
    nodeoutbound_qs = models.NodeOutbound.objects.filter(node=node_obj).select_related("group")
    for i in nodeoutbound_qs:
        res.append(
            {
                "tag": i.name,
                "conf": django.template.Template(i.xray_outbound_template).render(context=django.template.Context({})),
            }
        )
        balancers[i.group.name].append(i.name)
    balancers_res = ", ".join(
        [
            """
    {{
      "tag": "{}",
      "selector": [{}]
    }}
    """.format(
                tag, ", ".join([f'"{i}"' for i in selectors])
            )
            for tag, selectors in balancers.items()
        ]
    )
    return res, balancers_res


def get_connectable_subscriptionperiod_qs():
    return (
        models.SubscriptionPeriod.objects.ann_expires_at()
        .ann_dl_bytes_remained()
        .ann_up_bytes_remained()
        .filter(
            Q(selected_as_current=True, profile__is_active=True, expires_at__gt=timezone.now())
            & Q(Q(up_bytes_remained__gt=0) | Q(dl_bytes_remained__gt=0))
        )
    )


def get_xray_conf(node_obj) -> tuple[str, str, dict]:
    proxy_manager_config = models.Config.objects.get()
    inbound_parts = ""
    rule_parts = ""

    for inbound in models.Inbound.objects.filter(is_active=True, is_template=False):
        xray_inbound = django.template.Template("{% load node_manager %}" + inbound.inbound_template).render(
            context=django.template.Context({"node": node_obj})
        )
        if inbound_parts:
            inbound_parts += ",\n"
        inbound_parts += xray_inbound
    xray_outbounds, balancer_parts = get_xray_outbounds(node_obj=node_obj)
    for connection_rule in models.ConnectionRule.objects.filter():
        subscriptionperiods_obj_list = list(
            get_connectable_subscriptionperiod_qs().filter(plan__connection_rule=connection_rule)
        )
        inbound_tags = []
        for inbound in models.Inbound.objects.filter(is_active=True, is_template=True):
            inbound_tag = f"{inbound.name}-{connection_rule.id}"
            consumers_part = ""
            for subscriptionperiod_obj in subscriptionperiods_obj_list:
                consumer_obj = django.template.Template(
                    "{% load node_manager proxy_manager %}" + inbound.consumer_obj_template
                ).render(context=django.template.Context({"subscriptionperiod_obj": subscriptionperiod_obj}))
                if consumers_part:
                    consumers_part += ",\n"
                consumers_part += consumer_obj

            xray_inbound = django.template.Template(
                "{% load node_manager proxy_manager %}" + inbound.inbound_template
            ).render(
                context=django.template.Context(
                    {"node": node_obj, "inbound_tag": inbound_tag, "consumers_part": consumers_part}
                )
            )
            inbound_tags.append(inbound_tag)
            if inbound_parts:
                inbound_parts += ",\n"
            inbound_parts += xray_inbound
        xray_rules = django.template.Template(
            "{% load node_manager proxy_manager %}" + connection_rule.xray_rules_template
        ).render(
            context=django.template.Context(
                {"node": node_obj, "inbound_tags": inbound_tags, "outbound_tags": [i["tag"] for i in xray_outbounds]}
            )
        )
        if rule_parts:
            rule_parts += ", \n"
        rule_parts += xray_rules

    context = django.template.Context(
        {
            "node": node_obj,
            "inbound_parts": inbound_parts,
            "rule_parts": rule_parts,
            "outbound_parts": [i["conf"] for i in xray_outbounds],
            "balancer_parts": balancer_parts,
        }
    )
    xray_config_template = "{% load node_manager proxy_manager %}" + proxy_manager_config.xray_config_template
    result = django.template.Template(xray_config_template).render(context=context)
    run_opt = django.template.Template("-c *#path:main#*").render(context=context)
    return run_opt, result, context.get("deps", {"globals": []})
