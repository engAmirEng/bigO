from collections import defaultdict

import django.template

from bigO.core import models as core_models
from bigO.node_manager import models as node_manager_models
from bigO.node_manager import services as node_manager_services, typing as node_manager_typing
from bigO.node_manager import typing as node_manager_typing
from django.db.models import Q
from django.utils import timezone
import pathlib
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


def get_xray_conf(node_obj, node_work_dir: pathlib.Path, host_name: str) -> tuple[str, list[node_manager_typing.FileSchema]] | None:
    site_config: core_models.SiteConfiguration = core_models.SiteConfiguration.objects.get()
    if not node_obj.tmp_xray:
        return None
    elif site_config.main_xray is None:
        logger.critical("no program set for xray_conf")
        return None
    xray_program = site_config.main_xray.get_program_for_node(node_obj)
    if xray_program is None:
        raise node_manager_services.ProgramNotFound(program_version=site_config.main_xray)
    elif isinstance(xray_program, models.ProgramBinary):
        dest_path = node_work_dir.joinpath("bin", f"{xray_program.id}_{xray_program.hash[:6]}")
        xray_program_file = node_manager_typing.FileSchema(
            dest_path=dest_path,
            url=get_absolute_url(
                reverse("node_manager:node_program_binary_content_by_hash", args=[xray_program.hash])
            ),
            permission=node_manager_services.all_permission,
            hash=xray_program.hash,
        )
    elif isinstance(xray_program, models.NodeInnerProgram):
        xray_program_file = node_manager_typing.FileSchema(
            dest_path=xray_program.path,
            permission=node_manager_services.all_permission,
        )
    else:
        raise AssertionError
    files = []
    files.append(xray_program_file)

    proxy_manager_config = models.Config.objects.get()
    inbound_parts = ""
    rule_parts = ""

    for inbound in models.Inbound.objects.filter(is_active=True, is_template=False):
        template_context = django.template.Context({"node": node_obj})
        xray_inbound = django.template.Template("{% load node_manager %}" + inbound.inbound_template).render(
            context=template_context
        )
        new_files = node_manager_services.get_configdependentcontents_from_context(template_context)
        files.extend(new_files)
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
                template_context = django.template.Context({"subscriptionperiod_obj": subscriptionperiod_obj})
                consumer_obj = django.template.Template(
                    "{% load node_manager proxy_manager %}" + inbound.consumer_obj_template
                ).render(context=template_context)
                new_files = node_manager_services.get_configdependentcontents_from_context(template_context)
                files.extend(new_files)
                if consumers_part:
                    consumers_part += ",\n"
                consumers_part += consumer_obj

            template_context = django.template.Context(
                {"node": node_obj, "inbound_tag": inbound_tag, "consumers_part": consumers_part}
            )
            xray_inbound = django.template.Template(
                "{% load node_manager proxy_manager %}" + inbound.inbound_template
            ).render(context=template_context)
            new_files = node_manager_services.get_configdependentcontents_from_context(template_context)
            files.extend(new_files)
            inbound_tags.append(inbound_tag)
            if inbound_parts:
                inbound_parts += ",\n"
            inbound_parts += xray_inbound

        template_context = django.template.Context(
            {"node": node_obj, "inbound_tags": inbound_tags, "outbound_tags": [i["tag"] for i in xray_outbounds]}
        )
        xray_rules = django.template.Template(
            "{% load node_manager proxy_manager %}" + connection_rule.xray_rules_template
        ).render(context=template_context)
        new_files = node_manager_services.get_configdependentcontents_from_context(template_context)
        files.extend(new_files)
        if rule_parts:
            rule_parts += ", \n"
        rule_parts += xray_rules

    template_context = django.template.Context(
        {
            "node": node_obj,
            "inbound_parts": inbound_parts,
            "rule_parts": rule_parts,
            "outbound_parts": [i["conf"] for i in xray_outbounds],
            "balancer_parts": balancer_parts,
        }
    )
    xray_config_template = "{% load node_manager proxy_manager %}" + proxy_manager_config.xray_config_template
    xray_config_content = django.template.Template(xray_config_template).render(context=template_context)
    xray_config_content_hash = sha256(xray_config_content.encode("utf-8")).hexdigest()
    xray_config_content_file = node_manager_typing.FileSchema(
        dest_path=f"xray_{xray_config_content_hash[:6]}.json",
        content=xray_config_content,
        hash=xray_config_content_hash,
        permission=node_manager_services.all_permission,
    )
    files.append(xray_config_content_file)

    new_files = node_manager_services.get_configdependentcontents_from_context(template_context)
    files.extend(new_files)
    supervisor_config = f"""
# config={timezone.now()}
[program:xray_conf]
command={xray_program_file.dest_path} -c {xray_config_content_file.dest_path}
autostart=true
autorestart=true
priority=10
"""
    return supervisor_config, files


def get_agent_current_subscriptionperiods_qs(agent: models.Agent):
    return models.SubscriptionPeriod.objects.filter(
        profile__initial_agency_id=agent.agency_id, selected_as_current=True
    )
