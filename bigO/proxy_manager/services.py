import datetime
import logging
import pathlib
from collections import defaultdict
from hashlib import sha256

import django.template
from bigO.core import models as core_models
from bigO.node_manager import models as node_manager_models
from bigO.node_manager import services as node_manager_services
from bigO.node_manager import typing as node_manager_typing
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from . import models

logger = logging.getLogger(__name__)


def get_proxy_manager_nginx_conf_v1(node_obj) -> tuple[str, str, dict] | None:
    if not node_obj.tmp_xray:
        return None
    proxy_manager_config = models.Config.objects.get()
    context = django.template.Context({"node_obj": node_obj})
    nginx_config_http_template = "{% load node_manager %}" + proxy_manager_config.nginx_config_http_template
    nginx_config_http_result = django.template.Template(nginx_config_http_template).render(context=context)
    nginx_config_stream_template = "{% load node_manager %}" + proxy_manager_config.nginx_config_stream_template
    nginx_config_stream_result = django.template.Template(nginx_config_stream_template).render(context=context)
    return nginx_config_http_result, nginx_config_stream_result, context.get("deps", {"globals": []})


def get_proxy_manager_nginx_conf_v2(
    node_obj, xray_path_matchers_parts: list, node_work_dir: pathlib.Path, base_url: str
) -> tuple[str, str, list[node_manager_typing.FileSchema]] | None:
    if not node_obj.tmp_xray:
        return None
    proxy_manager_config = models.Config.objects.get()
    template_context = node_manager_services.NodeTemplateContext(
        {"node_obj": node_obj, "xray_path_matchers": "\n".join(xray_path_matchers_parts)},
        node_work_dir=node_work_dir,
        base_url=base_url,
    )
    nginx_config_http_template = "{% load node_manager %}" + proxy_manager_config.nginx_config_http_template
    nginx_config_http_result = django.template.Template(nginx_config_http_template).render(context=template_context)
    nginx_config_stream_template = "{% load node_manager %}" + proxy_manager_config.nginx_config_stream_template
    nginx_config_stream_result = django.template.Template(nginx_config_stream_template).render(
        context=template_context
    )
    new_files = node_manager_services.get_configdependentcontents_from_context(template_context)
    return nginx_config_http_result, nginx_config_stream_result, new_files


def get_xray_outbounds(node_obj):
    res = []
    balancers = defaultdict(list)
    nodeoutbound_qs = models.NodeOutbound.objects.filter(node=node_obj).select_related("group")
    for i in nodeoutbound_qs:
        res.append(
            {
                "tag": i.name,
                "conf": django.template.Template(i.xray_outbound_template).render(context=django.template.Context({"tag": i.name, "node": node_obj})),
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


def get_xray_conf_v2(
    node_obj, node_work_dir: pathlib.Path, base_url: str
) -> tuple[str, list[node_manager_typing.FileSchema], dict[str, list]] | None:
    site_config: core_models.SiteConfiguration = core_models.SiteConfiguration.objects.get()
    if not node_obj.tmp_xray:
        return None
    elif site_config.main_xray is None:
        logger.critical("no program set for xray_conf")
        return None
    xray_program = site_config.main_xray.get_program_for_node(node_obj)
    if xray_program is None:
        raise node_manager_services.ProgramNotFound(program_version=site_config.main_xray)
    elif isinstance(xray_program, node_manager_models.ProgramBinary):
        dest_path = node_work_dir.joinpath("bin", f"{xray_program.id}_{xray_program.hash[:6]}")
        xray_program_file = node_manager_typing.FileSchema(
            dest_path=dest_path,
            url=base_url + reverse("node_manager:node_program_binary_content_by_hash", args=[xray_program.hash]),
            permission=node_manager_services.all_permission,
            hash=xray_program.hash,
        )
    elif isinstance(xray_program, node_manager_models.NodeInnerProgram):
        xray_program_file = node_manager_typing.FileSchema(
            dest_path=xray_program.path,
            permission=node_manager_services.all_permission,
        )
    else:
        raise AssertionError
    files = []
    files.append(xray_program_file)

    haproxy_backends_parts = []
    haproxy_80_matchers_parts = []
    haproxy_443_matchers_parts = []
    nginx_path_matchers_parts = []

    proxy_manager_config = models.Config.objects.get()
    inbound_parts = ""
    rule_parts = ""

    xray_outbounds, balancer_parts = get_xray_outbounds(node_obj=node_obj)

    all_subscriptionperiods_obj_list = get_connectable_subscriptionperiod_qs().select_related("plan")
    all_internaluser_ob_list = models.InternalUser.objects.filter(is_active=True).exclude(
        node=node_obj
    )
    all_proxyusers_list = [
        *[(i, i.plan.connection_rule_id, i.resource_pool_id) for i in all_subscriptionperiods_obj_list],
        *[(i, i.connection_rule_id, i.resource_pool_id) for i in all_internaluser_ob_list],
    ]
    connection_rule_id_proxyusers: dict[int, set[models.SubscriptionPeriod | models.InternalUser]] = defaultdict(set)

    inbound_tags = []
    for inbound in models.InboundType.objects.filter(is_active=True):
        inbound_tag = inbound.name
        consumers_part = ""
        for proxyuser, connection_rule_id, resource_pool_id in all_proxyusers_list:
            connection_rule_id_proxyusers[connection_rule_id].add(proxyuser)
            template_context = node_manager_services.NodeTemplateContext(
                {"subscriptionperiod_obj": proxyuser}, node_work_dir=node_work_dir, base_url=base_url
            )
            consumer_obj = django.template.Template(
                "{% load node_manager proxy_manager %}" + inbound.consumer_obj_template
            ).render(context=template_context)
            new_files = node_manager_services.get_configdependentcontents_from_context(template_context)
            files.extend(new_files)
            if consumers_part:
                consumers_part += ",\n"
            consumers_part += consumer_obj

        template_context = node_manager_services.NodeTemplateContext(
            {
                "node": node_obj,
                "inbound_tag": inbound_tag,
                "consumers_part": consumers_part,
            },
            node_work_dir=node_work_dir,
            base_url=base_url,
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

        if inbound.haproxy_backend:
            haproxy_backends_parts.append(inbound.haproxy_backend)
        if inbound.haproxy_matcher_80:
            haproxy_80_matchers_parts.append(inbound.haproxy_matcher_80)
        if inbound.haproxy_matcher_443:
            haproxy_443_matchers_parts.append(inbound.haproxy_matcher_443)
        if inbound.nginx_path_config:
            nginx_path_matchers_parts.append(inbound.nginx_path_config)

    for connection_rule in models.ConnectionRule.objects.filter():
        proxyusers_obj_list = connection_rule_id_proxyusers[connection_rule.id][connectionruleresourcepool.id]
        if not proxyusers_obj_list:
            # because the routing will be messed up
            continue

        template_context = node_manager_services.NodeTemplateContext(
            {
                "node": node_obj,
                "subscriptionperiods": proxyusers_obj_list,
                "inbound_tags": inbound_tags,
                "outbound_tags": [i["tag"] for i in xray_outbounds],
            },
            node_work_dir=node_work_dir,
            base_url=base_url,
        )
        xray_rules = django.template.Template(
            "{% load node_manager proxy_manager %}" + connection_rule.xray_rules_template
        ).render(context=template_context)
        new_files = node_manager_services.get_configdependentcontents_from_context(template_context)
        files.extend(new_files)
        if rule_parts:
            rule_parts += ", \n"
        rule_parts += xray_rules

    template_context = node_manager_services.NodeTemplateContext(
        {
            "node": node_obj,
            "inbound_parts": inbound_parts,
            "rule_parts": rule_parts,
            "outbound_parts": [i["conf"] for i in xray_outbounds],
            "balancer_parts": balancer_parts,
        },
        node_work_dir=node_work_dir,
        base_url=base_url,
    )
    xray_config_template = "{% load node_manager proxy_manager %}" + proxy_manager_config.xray_config_template
    xray_config_content = django.template.Template(xray_config_template).render(context=template_context)
    xray_config_content_hash = sha256(xray_config_content.encode("utf-8")).hexdigest()
    xray_config_content_file = node_manager_typing.FileSchema(
        dest_path=node_work_dir.joinpath("conf", f"xray_{xray_config_content_hash[:6]}.json"),
        content=xray_config_content,
        hash=xray_config_content_hash,
        permission=node_manager_services.all_permission,
    )
    files.append(xray_config_content_file)

    new_files = node_manager_services.get_configdependentcontents_from_context(template_context)

    assets_dir_hash = sha256()
    geosite_file = None
    if proxy_manager_config.geosite:
        geosite_file = proxy_manager_config.geosite.get_program_for_node(node_obj)
        if not isinstance(geosite_file, node_manager_models.ProgramBinary):
            raise NotImplementedError
        assets_dir_hash.update(geosite_file.hash.encode())
    geoip_file = None
    if proxy_manager_config.geosite:
        geoip_file = proxy_manager_config.geoip.get_program_for_node(node_obj)
        if not isinstance(geoip_file, node_manager_models.ProgramBinary):
            raise NotImplementedError
        assets_dir_hash.update(geoip_file.hash.encode())

    assets_dir = node_work_dir.joinpath("bin", f"x_assets_{assets_dir_hash.hexdigest()[:6]}")
    if geosite_file:
        url = base_url + reverse("node_manager:node_program_binary_content_by_hash", args=[geosite_file.hash])
        files.append(
            node_manager_typing.FileSchema(
                dest_path=assets_dir.joinpath("geosite.dat"),
                url=url,
                hash=geosite_file.hash,
                permission=node_manager_services.all_permission,
            )
        )
    if geoip_file:
        url = base_url + reverse("node_manager:node_program_binary_content_by_hash", args=[geoip_file.hash])
        files.append(
            node_manager_typing.FileSchema(
                dest_path=assets_dir.joinpath("geoip.dat"),
                url=url,
                hash=geoip_file.hash,
                permission=node_manager_services.all_permission,
            )
        )

    files.extend(new_files)
    supervisor_config = f"""
# config={timezone.now()}
[program:xray_conf]
command={xray_program_file.dest_path} -c {xray_config_content_file.dest_path}
environment=XRAY_LOCATION_ASSET={assets_dir}
autostart=true
autorestart=true
priority=10
"""
    return (
        supervisor_config,
        files,
        {
            "haproxy_backends_parts": haproxy_backends_parts,
            "haproxy_80_matchers_parts": haproxy_80_matchers_parts,
            "haproxy_443_matchers_parts": haproxy_443_matchers_parts,
            "nginx_path_matchers_parts": nginx_path_matchers_parts,
        },
    )


def get_agent_current_subscriptionperiods_qs(agent: models.Agent):
    return models.SubscriptionPeriod.objects.filter(
        profile__initial_agency_id=agent.agency_id, selected_as_current=True
    )


def set_profile_last_stat(
    sub_profile_id: str, sub_profile_period_id: str, collect_time: datetime.datetime
) -> models.SubscriptionPeriod:
    subscriptionperiod = models.SubscriptionPeriod.objects.get(id=sub_profile_period_id, profile_id=sub_profile_id)
    if subscriptionperiod.first_usage_at is None:
        subscriptionperiod.first_usage_at = collect_time
    if subscriptionperiod.first_usage_at > collect_time:
        subscriptionperiod.first_usage_at = collect_time

    if subscriptionperiod.last_usage_at is None:
        subscriptionperiod.last_usage_at = collect_time
    if subscriptionperiod.last_usage_at < collect_time:
        subscriptionperiod.last_usage_at = collect_time
    subscriptionperiod.save()
    return subscriptionperiod
