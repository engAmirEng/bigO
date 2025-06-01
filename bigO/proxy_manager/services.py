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
from django.db.models import Prefetch, Q
from django.urls import reverse
from django.utils import timezone

from . import models, typing

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

    connectionrule_qs = (
        models.ConnectionRule.objects.filter(rule_nodeoutbounds__node=node_obj)
        .prefetch_related(
            Prefetch(
                "rule_nodeoutbounds",
                to_attr="node_connection_outbounds",
                queryset=models.NodeOutbound.objects.filter(node=node_obj).select_related("inbound_spec"),
            )
        )
        .distinct()
    )
    # connectionrule_outbound_qs = list(models.ConnectionRuleOutbound.objects.filter(node_outbound__node=node_obj).select_related("rule"))
    if not connectionrule_qs:
        return None

    all_subscriptionperiods_obj_list = (
        get_connectable_subscriptionperiod_qs()
        .filter(plan__connection_rule_id__in=[i.id for i in connectionrule_qs])
        .select_related("plan")
    )
    all_nodeinternaluser_ob_list = models.InternalUser.objects.filter(
        is_active=True, connection_rule_id__in=[i.id for i in connectionrule_qs]
    ).exclude(node=node_obj)
    all_proxyusers_list: list[tuple[typing.ProxyUserProtocol, int]] = [
        *[(i, i.plan.connection_rule_id) for i in all_subscriptionperiods_obj_list],
        *[(i, i.connection_rule_id) for i in all_nodeinternaluser_ob_list],
    ]
    connection_rule_id_proxyusers: dict[int, set[typing.ProxyUserProtocol]] = defaultdict(set)

    inbound_tags = []
    for inbound in models.InboundType.objects.filter(is_active=True):
        inbound_tag = inbound.name
        consumers_part = ""
        for proxyuser, connection_rule_id in all_proxyusers_list:
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
                "node_obj": node_obj,
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
        if xray_inbound:
            if inbound_parts:
                inbound_parts += ",\n"
            inbound_parts += xray_inbound

        if inbound.haproxy_backend:
            haproxy_backends_parts.append(
                django.template.Template(inbound.haproxy_backend).render(
                    context=django.template.Context({"node_obj": node_obj})
                )
            )
        if inbound.haproxy_matcher_80:
            haproxy_80_matchers_parts.append(
                django.template.Template(inbound.haproxy_matcher_80).render(
                    context=django.template.Context({"node_obj": node_obj})
                )
            )
        if inbound.haproxy_matcher_443:
            haproxy_443_matchers_parts.append(
                django.template.Template(inbound.haproxy_matcher_443).render(
                    context=django.template.Context({"node_obj": node_obj})
                )
            )
        if inbound.nginx_path_config:
            nginx_path_matchers_parts.append(
                django.template.Template(inbound.nginx_path_config).render(
                    context=django.template.Context({"node_obj": node_obj})
                )
            )

    all_xray_outbounds = {}
    all_xray_balancers = {}
    for connection_rule in connectionrule_qs:
        proxyusers_obj_list = connection_rule_id_proxyusers[connection_rule.id]
        if not proxyusers_obj_list:
            # because the routing will be messed up
            continue

        nodeinternaluser = models.InternalUser.objects.filter(connection_rule=connection_rule, node=node_obj).first()
        if nodeinternaluser is None:
            nodeinternaluser = models.InternalUser.init_for_node(node=node_obj, connection_rule=connection_rule)
        if nodeinternaluser and not nodeinternaluser.is_active:
            nodeinternaluser = None
        xray_outbounds = {}
        xray_balancers = defaultdict(list)
        for nodeoutbound in connection_rule.node_connection_outbounds:
            is_outbound_used = False
            nodeoutbound: models.NodeOutbound
            outbound_tag = f"{connection_rule.id}_{nodeoutbound.to_inbound_type.name if nodeoutbound.to_inbound_type else ''}_{nodeoutbound.name}"
            balancer_allocations = nodeoutbound.get_balancer_allocations()
            for balancer_allocation in balancer_allocations:
                balancer_tag = f"{connection_rule.id}_{balancer_allocation[0]}"
                for i in range(balancer_allocation[1]):
                    is_outbound_used = True
                    xray_balancers[balancer_tag].append(outbound_tag)
            if not is_outbound_used:
                continue
            if nodeoutbound.inbound_spec:
                combo_stat = nodeoutbound.inbound_spec.get_combo_stat()
            else:
                combo_stat = None
            xray_outbounds[outbound_tag] = django.template.Template(nodeoutbound.xray_outbound_template).render(
                django.template.Context(
                    {
                        "tag": outbound_tag,
                        "node": node_obj,
                        "nodeinternaluser": nodeinternaluser,
                        "combo_stat": combo_stat,
                    }
                )
            )
        all_xray_outbounds = {**all_xray_outbounds, **xray_outbounds}
        all_xray_balancers = {**all_xray_balancers, **xray_balancers}

        template_context = node_manager_services.NodeTemplateContext(
            {
                "node": node_obj,
                "connection_rule": connection_rule,
                "subscriptionperiods": proxyusers_obj_list,
                "inbound_tags": inbound_tags,
                "outbound_tags": list(xray_outbounds.keys()),
                "xray_balancers": xray_balancers,
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

    all_balancer_parts = ",\n".join(
        [
            '{{"tag": "{0}", "selector": [{1}]}}'.format(tag, ",".join([f'"{i}"' for i in selectors]))
            for tag, selectors in all_xray_balancers.items()
        ]
    )

    template_context = node_manager_services.NodeTemplateContext(
        {
            "node": node_obj,
            "inbound_parts": inbound_parts,
            "rule_parts": rule_parts,
            "outbound_parts": list(all_xray_outbounds.values()),
            "balancer_parts": all_balancer_parts,
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
) -> models.SubscriptionPeriod | None:
    subscriptionperiod = models.SubscriptionPeriod.objects.filter(
        id=sub_profile_period_id, profile_id=sub_profile_id
    ).first()
    if subscriptionperiod is None:
        logger.critical(f"no SubscriptionPeriod found with {sub_profile_id=} and {sub_profile_period_id=}")
        return None
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


def set_internal_user_last_stat(
    rule_id: str, node_user_id: str, collect_time: datetime.datetime
) -> models.InternalUser | None:
    internaluser = models.InternalUser.objects.filter(connection_rule_id=rule_id, node_id=node_user_id).first()
    if internaluser is None:
        logger.critical(f"no InternalUser found with {rule_id=} and {node_user_id=}")
        return
    if internaluser.first_usage_at is None:
        internaluser.first_usage_at = collect_time
    if internaluser.first_usage_at > collect_time:
        internaluser.first_usage_at = collect_time

    if internaluser.last_usage_at is None:
        internaluser.last_usage_at = collect_time
    if internaluser.last_usage_at < collect_time:
        internaluser.last_usage_at = collect_time
    internaluser.save()
    return internaluser
