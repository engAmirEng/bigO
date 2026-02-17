import json
import logging
import pathlib
import random
import re
from collections import defaultdict
from decimal import ROUND_HALF_DOWN, Decimal
from hashlib import sha256
from typing import Protocol

import sentry_sdk

import django.template
from bigO.core import models as core_models
from bigO.node_manager import models as node_manager_models
from bigO.node_manager import services as node_manager_services
from bigO.node_manager import typing as node_manager_typing
from django.db.models import Prefetch, Q
from django.urls import reverse
from django.utils import timezone

from .. import models, services, typing

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


def get_connection_tunnel(node_obj: node_manager_models.Node):
    inbound_parts = ""
    rule_parts = ""
    proxyusers = []
    xray_balancers: dict[str, list[typing.BalancerMemberType]] = defaultdict(list)
    xray_outbounds = {}
    xray_portals: list[dict] = []
    xray_bridges: list[dict] = []
    portal_rules_parts: list[dict] = []
    bridge_first_rules_parts: list[dict] = []
    bridge_second_rules_parts: list[dict] = []
    all_balancer_parts = ""

    source_node_connectiontunnel_qs = (
        models.ConnectionTunnel.objects.filter(source_node=node_obj, tunnel_localtunnelports__isnull=False)
        .prefetch_related(
            Prefetch(
                "tunnel_localtunnelports",
                to_attr="localtunnelports",
            ),
            Prefetch(
                "tunnel_outbounds",
                to_attr="direct_tunnel_outbounds_list",
                queryset=models.ConnectionTunnelOutbound.objects.filter(weight__gt=0, is_reverse=False).select_related(
                    "connector__outbound_type", "connector__inbound_spec"
                ),
            ),
            Prefetch(
                "tunnel_outbounds",
                to_attr="portal_reverse_list",
                queryset=models.ConnectionTunnelOutbound.objects.filter(weight__gt=0, is_reverse=True).select_related(
                    "connector__outbound_type", "connector__inbound_spec"
                ),
            ),
        )
        .distinct()
    )
    dest_node_connectiontunnel_qs = models.ConnectionTunnel.objects.filter(dest_node=node_obj).prefetch_related(
        Prefetch(
            "tunnel_outbounds",
            to_attr="direct_tunnel_outbounds_list",
            queryset=models.ConnectionTunnelOutbound.objects.filter(weight__gt=0, is_reverse=False).select_related(
                "connector__outbound_type", "connector__inbound_spec"
            ),
        ),
        Prefetch(
            "tunnel_outbounds",
            to_attr="bridge_reverse_list",
            queryset=models.ConnectionTunnelOutbound.objects.filter(weight__gt=0, is_reverse=True).select_related(
                "connector__outbound_type", "connector__inbound_spec"
            ),
        ),
    )
    dokodemo_template = """
        {
            "listen": "0.0.0.0",
            "port": {{ local_port }},
            "protocol": "dokodemo-door",  # "tunnel" from 25.8.3
            "settings": {
              "address": "{{ dest_addr }}",
              "port": {{ dest_port }},
              "network": "tcp"
             },
            "tag": "{{ inbound_tag }}"
          }
          """
    rule_template = """
    {
        "type": "field",
        "outboundTag": null,
        "inboundTag": [{{ inbounds|safe }}],
        "balancerTag": "{{ balancer_tag }}"
    }
    """

    for connectiontunnel in source_node_connectiontunnel_qs:
        connectiontunnel: models.ConnectionTunnel
        inbound_tags = []
        balancer_tag = f"tunn_{connectiontunnel.id}"
        for localtunnelport in connectiontunnel.localtunnelports:
            localtunnelport: models.LocalTunnelPort
            inbound_tag = f"tcp_udp_in_{localtunnelport.local_port}"
            inbound_tags.append(inbound_tag)
            if localtunnelport.dest_node:
                dest_node_nodepublicip = (
                    localtunnelport.dest_node.node_nodepublicips.filter(ip__ip__family=4).select_related("ip").first()
                )
                if dest_node_nodepublicip:
                    dest_addr = dest_node_nodepublicip.ip.ip.ip
                else:
                    sentry_sdk.capture_message(
                        f"skipping {localtunnelport.id=} of {connectiontunnel.id=} since no destip"
                    )
                    continue
            else:
                dest_addr = "127.0.0.1"
            inbound_part = django.template.Template(dokodemo_template).render(
                django.template.Context(
                    {
                        "local_port": localtunnelport.local_port,
                        "dest_port": localtunnelport.dest_port,
                        "dest_addr": dest_addr,
                        "inbound_tag": inbound_tag,
                    }
                )
            )
            if inbound_parts:
                inbound_parts = inbound_parts + ",\n" + inbound_part
            else:
                inbound_parts = inbound_part

        rule_part = django.template.Template(rule_template).render(
            django.template.Context(
                {"balancer_tag": balancer_tag, "inbounds": ", ".join([f'"{i}"' for i in inbound_tags])}
            )
        )
        if rule_parts:
            rule_parts = rule_parts + ",\n" + rule_part
        else:
            rule_parts = rule_part

        nodeinternaluser = connectiontunnel.get_nodeinternaluser()
        for direct_tunnel_outbound in connectiontunnel.direct_tunnel_outbounds_list:
            direct_tunnel_outbound: models.ConnectionTunnelOutbound
            assert not direct_tunnel_outbound.is_reverse
            if not direct_tunnel_outbound.weight > 0:
                continue
            outbound_tag = XrayOutBound.get_node_tunn_outbound_name(
                connectiontunnel=connectiontunnel, outbound=direct_tunnel_outbound
            )

            xray_balancers[balancer_tag].append({"tag": outbound_tag, "weight": direct_tunnel_outbound.weight})
            if direct_tunnel_outbound.connector.inbound_spec:
                combo_stat = direct_tunnel_outbound.connector.inbound_spec.get_combo_stat()
            else:
                combo_stat = None
            xray_outbounds[outbound_tag] = django.template.Template(
                direct_tunnel_outbound.connector.outbound_type.xray_outbound_template
            ).render(
                django.template.Context(
                    {
                        "tag": outbound_tag,
                        "source_node": connectiontunnel.source_node,
                        "dest_node": connectiontunnel.dest_node,
                        "nodeinternaluser": nodeinternaluser,
                        "combo_stat": combo_stat,
                    }
                )
            )
        for portal_reverse in connectiontunnel.portal_reverse_list:
            portal_reverse: models.ConnectionTunnelOutbound
            assert portal_reverse.is_reverse
            balancer_tag = f"tunn_{connectiontunnel.id}"
            if not portal_reverse.weight > 0:
                continue
            portal_tag = XrayOutBound.get_tunn_portal_outbound_name(
                connectiontunnel=connectiontunnel,
                portal_reverse=portal_reverse,
            )
            xray_portals.append(
                {
                    "tag": portal_tag,
                    "domain": portal_reverse.get_domain_for_balancer_tag(),
                }
            )
            reverse_proxyuser = portal_reverse.get_proxyuser_balancer_tag()
            proxyusers.append(reverse_proxyuser)
            portal_rules_parts.append(
                {"type": "field", "user": [reverse_proxyuser.xray_email()], "outboundTag": portal_tag}
            )
            xray_balancers[balancer_tag].append({"tag": portal_tag, "weight": portal_reverse.weight})
        balancer_parts = ",\n".join(
            [
                '{{"tag": "{0}", "selector": [{1}], "strategy": {2}, "fallbackTag": "{3}"}}'.format(
                    tag,
                    ",".join(
                        [
                            f'"{balancer_member["tag"]}"'
                            for balancer_member in sorted(
                                balancer_members, key=lambda x: sha256(x["tag"].encode("utf-8")).hexdigest()
                            )
                        ]
                    ),
                    *get_strategy_part(balancer_members, balancer_obj=connectiontunnel.balancer),
                )
                for tag, balancer_members in xray_balancers.items()
            ]
        )
        if all_balancer_parts:
            all_balancer_parts += ",\n" + balancer_parts
        else:
            all_balancer_parts = balancer_parts

    for connectiontunnel in dest_node_connectiontunnel_qs:
        connectiontunnel: models.ConnectionTunnel
        nodeinternaluser = connectiontunnel.get_nodeinternaluser()
        proxyusers.append(nodeinternaluser)

        for bridge_reverse in connectiontunnel.bridge_reverse_list:
            bridge_reverse: models.ConnectionTunnelOutbound
            assert bridge_reverse.is_reverse
            if not bridge_reverse.weight > 0:
                continue
            reverse_proxyuser = bridge_reverse.get_proxyuser_balancer_tag()
            proxyusers.append(reverse_proxyuser)
            bridge_tag, interconn_outbound_tag = XrayOutBound.get_tunn_bridge_outbound_name(
                connectiontunnel=connectiontunnel,
                bridge_reverse=bridge_reverse,
            )
            reverse_domain = bridge_reverse.get_domain_for_balancer_tag()
            xray_bridges.append({"tag": bridge_tag, "domain": reverse_domain})
            reverse_proxyuser = bridge_reverse.get_proxyuser_balancer_tag()
            if bridge_reverse.connector.inbound_spec:
                combo_stat = bridge_reverse.connector.inbound_spec.get_combo_stat()
            else:
                combo_stat = None
            xray_outbounds[interconn_outbound_tag] = django.template.Template(
                bridge_reverse.connector.outbound_type.xray_outbound_template
            ).render(
                django.template.Context(
                    {
                        "tag": interconn_outbound_tag,
                        "source_node": connectiontunnel.source_node,
                        "dest_node": connectiontunnel.dest_node,
                        "nodeinternaluser": reverse_proxyuser,
                        "combo_stat": combo_stat,
                    }
                )
            )
            bridge_first_rules_parts.append(
                {
                    "type": "field",
                    "inboundTag": [bridge_tag],
                    "domain": [f"full:{reverse_domain}"],
                    "outboundTag": interconn_outbound_tag,
                }
            )
            bridge_second_rules_parts.append({"type": "field", "inboundTag": [bridge_tag], "outboundTag": "freedom"})

    if proxyusers:
        to_tunnel_rule_part = """
        {{
            "type":"field",
            "outboundTag": "freedom",
            "user": [{users}]
        }}
        """.format(
            users=",".join([f'"{i.xray_email()}"' for i in proxyusers])
        )
        if rule_parts:
            rule_parts = rule_parts + ",\n" + to_tunnel_rule_part
        else:
            rule_parts = to_tunnel_rule_part

    return (
        proxyusers,
        portal_rules_parts,
        bridge_first_rules_parts,
        bridge_second_rules_parts,
        xray_bridges,
        xray_portals,
        inbound_parts,
        xray_outbounds,
        all_balancer_parts,
        rule_parts,
    )


XRAY_KEY = "xray"


@node_manager_services.process_conf.register_getter(key=XRAY_KEY, satisfies={node_manager_services.HAPROXY_KEY})
def get_xray_conf_v2(
    node_obj, node_work_dir: pathlib.Path, base_url: str, kwargs_list: list[dict]
) -> tuple[str, list[node_manager_typing.FileSchema], dict[str, dict]] | None:
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
    all_xray_outbounds = {}
    all_xray_balancers: dict[str, list[typing.BalancerMemberType]] = {}
    all_balancer_parts = ""
    reverse_proxyusers: list[typing.ProxyUserProtocol] = []
    portal_rules_parts: list[dict] = []
    xray_portals: list[dict] = []
    bridge_first_rules_parts: list[dict] = []
    bridge_second_rules_parts: list[dict] = []
    xray_bridges: list[dict] = []

    (
        tunn_all_users,
        tunn_portal_rules_parts,
        tunn_bridge_first_rules_parts,
        tunn_bridge_second_rules_parts,
        tunn_xray_bridges,
        tunn_xray_portals,
        tunn_inbound_parts,
        tunn_outbounds,
        tunn_balancer_parts,
        tunn_rule_parts,
    ) = get_connection_tunnel(node_obj=node_obj)
    if inbound_parts.strip():
        inbound_parts = inbound_parts + ",\n" + tunn_inbound_parts
    else:
        inbound_parts = tunn_inbound_parts
    if rule_parts.strip():
        rule_parts = tunn_rule_parts + ",\n" + rule_parts
    else:
        rule_parts = tunn_rule_parts
    if all_balancer_parts.strip():
        all_balancer_parts = all_balancer_parts + ",\n" + tunn_balancer_parts
    else:
        all_balancer_parts = tunn_balancer_parts
    xray_bridges.extend(tunn_xray_bridges)
    xray_portals.extend(tunn_xray_portals)
    portal_rules_parts.extend(tunn_portal_rules_parts)
    bridge_first_rules_parts.extend(tunn_bridge_first_rules_parts)
    bridge_second_rules_parts.extend(tunn_bridge_second_rules_parts)
    all_xray_outbounds.update(tunn_outbounds)

    private_rule_parts = """
    {
        "type":"field",
        "outboundTag": "freedom",
        "ip": [
          "geoip:private"
        ],
        "port": "53,80,443"
    },
    {
        "type": "field",
        "outboundTag": "blackhole",
        "ip": [
            "geoip:private"
        ]
    }
    """
    if rule_parts.strip():
        rule_parts = tunn_rule_parts + ",\n" + private_rule_parts
    else:
        rule_parts = private_rule_parts

    connectionrule_qs = (
        models.ConnectionRule.objects.filter(
            Q(rule_outbounds__apply_node=node_obj) | Q(rule_outbounds__connector__dest_node=node_obj)
        )  # just to filter down the results count
        .prefetch_related(
            Prefetch(
                "rule_outbounds",
                to_attr="node_connection_outbounds",
                queryset=models.ConnectionRuleOutbound.objects.filter(
                    apply_node=node_obj, is_reverse=False
                ).select_related("connector__outbound_type", "connector__inbound_spec"),
            ),
            Prefetch(
                "rule_outbounds",
                to_attr="bridge_connection_outbounds",
                queryset=models.ConnectionRuleOutbound.objects.filter(
                    apply_node=node_obj, is_reverse=True
                ).select_related("connector__outbound_type", "connector__inbound_spec"),
            ),
            Prefetch(
                "rule_outbounds",
                to_attr="portal_connection_outbounds",
                queryset=models.ConnectionRuleOutbound.objects.filter(
                    connector__dest_node=node_obj, is_reverse=True
                ).select_related("connector__outbound_type", "connector__inbound_spec"),
            ),
            Prefetch(
                "balancers",
                to_attr="balancers_list",
            ),
        )
        .distinct()
    )
    # connectionrule_outbound_qs = list(models.ConnectionRuleOutbound.objects.filter(node_outbound__node=node_obj).select_related("rule"))
    if not connectionrule_qs and not tunn_outbounds and not tunn_rule_parts and not tunn_inbound_parts:
        return None

    all_subscriptionperiods_obj_list = (
        services.get_connectable_subscriptionperiod_qs()
        .filter(plan__connection_rule_id__in=[i.id for i in connectionrule_qs])
        .select_related("plan")
    )
    all_nodeinternaluser_ob_list = models.InternalUser.objects.filter(
        is_active=True, connection_rule_id__in=[i.id for i in connectionrule_qs]
    ).exclude(node=node_obj)
    connection_rule_id_proxyusers: dict[int, set[typing.ProxyUserProtocol]] = defaultdict(set)
    for proxyuser, connection_rule_id in [
        *[(i, i.plan.connection_rule_id) for i in all_subscriptionperiods_obj_list],
        *[(i, i.connection_rule_id) for i in all_nodeinternaluser_ob_list],
    ]:
        connection_rule_id_proxyusers[connection_rule_id].add(proxyuser)

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
        xray_balancers: dict[str, list[typing.BalancerMemberType]] = defaultdict(list)
        for connection_outbound in connection_rule.node_connection_outbounds:
            assert not connection_outbound.is_reverse
            is_outbound_used = False
            connection_outbound: models.ConnectionRuleOutbound
            outbound_tag = XrayOutBound.get_node_outbound_name(
                connection_rule=connection_rule, nodeoutbound=connection_outbound
            )
            balancer_allocations = connection_outbound.get_balancer_allocations()
            for balancer_allocation in balancer_allocations:
                balancer_tag = f"{connection_rule.id}_{balancer_allocation[0]}"
                if balancer_allocation[1] > 0:
                    is_outbound_used = True
                    xray_balancers[balancer_tag].append({"tag": outbound_tag, "weight": balancer_allocation[1]})
            if not is_outbound_used:
                continue
            if connection_outbound.connector.inbound_spec:
                combo_stat = connection_outbound.connector.inbound_spec.get_combo_stat()
            else:
                combo_stat = None
            xray_outbounds[outbound_tag] = django.template.Template(
                connection_outbound.connector.outbound_type.xray_outbound_template
            ).render(
                django.template.Context(
                    {
                        "tag": outbound_tag,
                        "node": node_obj,
                        "nodeinternaluser": nodeinternaluser,
                        "combo_stat": combo_stat,
                    }
                )
            )

        for portal_connection_outbound in connection_rule.portal_connection_outbounds:
            assert portal_connection_outbound.is_reverse
            portal_connection_outbound: models.ConnectionRuleOutbound
            balancer_allocations = portal_connection_outbound.get_balancer_allocations()
            for balancer_allocation in balancer_allocations:
                is_reverse_used = False
                portal_tag = XrayOutBound.get_portal_outbound_name(
                    connection_rule=connection_rule,
                    portal_nodeoutbound=portal_connection_outbound,
                    balancer_allocation_idf=balancer_allocation[0],
                )
                balancer_tag = f"{connection_rule.id}_{balancer_allocation[0]}"
                if balancer_allocation[1] > 0:
                    is_reverse_used = True
                    xray_balancers[balancer_tag].append({"tag": portal_tag, "weight": balancer_allocation[1]})
                if not is_reverse_used:
                    continue
                xray_portals.append(
                    {
                        "tag": portal_tag,
                        "domain": portal_connection_outbound.get_domain_for_balancer_tag(balancer_tag=balancer_tag),
                    }
                )
                reverse_proxyuser = portal_connection_outbound.get_proxyuser_balancer_tag(balancer_tag=balancer_tag)
                reverse_proxyusers.append(reverse_proxyuser)
                portal_rules_parts.append(
                    {"type": "field", "user": [reverse_proxyuser.xray_email()], "outboundTag": portal_tag}
                )

        for bridge_connection_outbound in connection_rule.bridge_connection_outbounds:
            assert bridge_connection_outbound.is_reverse
            bridge_connection_outbound: models.ConnectionRuleOutbound
            balancer_allocations = bridge_connection_outbound.get_balancer_allocations()
            for balancer_allocation in balancer_allocations:
                is_reverse_used = False
                bridge_tag, interconn_outbound_tag = XrayOutBound.get_bridge_outbound_name(
                    connection_rule=connection_rule,
                    bridge_nodeoutbound=bridge_connection_outbound,
                    balancer_allocation_idf=balancer_allocation[0],
                )
                balancer_tag = f"{connection_rule.id}_{balancer_allocation[0]}"
                if balancer_allocation[1] > 0:
                    is_reverse_used = True
                if not is_reverse_used:
                    continue
                reverse_domain = bridge_connection_outbound.get_domain_for_balancer_tag(balancer_tag=balancer_tag)
                xray_bridges.append({"tag": bridge_tag, "domain": reverse_domain})
                reverse_proxyuser = bridge_connection_outbound.get_proxyuser_balancer_tag(balancer_tag=balancer_tag)
                if bridge_connection_outbound.connector.inbound_spec:
                    combo_stat = bridge_connection_outbound.connector.inbound_spec.get_combo_stat()
                else:
                    combo_stat = None
                xray_outbounds[interconn_outbound_tag] = django.template.Template(
                    bridge_connection_outbound.connector.outbound_type.xray_outbound_template
                ).render(
                    django.template.Context(
                        {
                            "tag": interconn_outbound_tag,
                            "node": node_obj,
                            "nodeinternaluser": reverse_proxyuser,
                            "combo_stat": combo_stat,
                        }
                    )
                )
                bridge_first_rules_parts.append(
                    {
                        "type": "field",
                        "inboundTag": [bridge_tag],
                        "domain": [f"full:{reverse_domain}"],
                        "outboundTag": interconn_outbound_tag,
                    }
                )
                bridge_second_rules_parts.append(
                    {"type": "field", "inboundTag": [bridge_tag], "balancerTag": balancer_tag}
                )

        all_xray_outbounds = {**all_xray_outbounds, **xray_outbounds}

        balancer_parts = ",\n".join(
            [
                '{{"tag": "{0}", "selector": [{1}], "strategy": {2}, "fallbackTag": "{3}"}}'.format(
                    tag,
                    ",".join(
                        [
                            f'"{balancer_member["tag"]}"'
                            for balancer_member in sorted(
                                balancer_members, key=lambda x: sha256(x["tag"].encode("utf-8")).hexdigest()
                            )
                        ]
                    ),
                    *get_strategy_part(
                        balancer_members,
                        balancer_obj=[i for i in connection_rule.balancers_list if i.name == tag.split("_")[-1]][0]
                        if [i for i in connection_rule.balancers_list if i.name == tag.split("_")[-1]]
                        else None,
                    ),
                )
                for tag, balancer_members in xray_balancers.items()
            ]
        )
        if all_balancer_parts:
            all_balancer_parts += ",\n" + balancer_parts
        else:
            all_balancer_parts = balancer_parts

        all_xray_balancers = {**all_xray_balancers, **xray_balancers}

        template_context = node_manager_services.NodeTemplateContext(
            {
                "node": node_obj,
                "connection_rule": connection_rule,
                "subscriptionperiods": proxyusers_obj_list,
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

    reverse_rule_parts = ",".join(
        [
            *[json.dumps(i, indent=4) for i in portal_rules_parts],
            *[json.dumps(i, indent=4) for i in bridge_first_rules_parts],
            *[json.dumps(i, indent=4) for i in bridge_second_rules_parts],
        ]
    )
    if reverse_rule_parts:
        rule_parts = reverse_rule_parts + "," + rule_parts

    inbound_tags = []
    inbounds = []
    for realityspec in models.RealitySpec.objects.filter(
        inbound_type__is_active=True, for_ip__ip_nodepublicips__node=node_obj
    ):
        extra_ctx = {"combo_stat": realityspec.get_combo_stat()}
        inbounds.append((realityspec.inbound_type, f"{realityspec.inbound_type.name}_rp{realityspec.id}", extra_ctx))
    for inboundtype in models.InboundType.objects.filter(is_active=True, is_template=True):
        inbounds.append((inboundtype, f"{inboundtype.name}", {"combo_stat": None}))
    for inbound, inbound_tag, extra_ctx in inbounds:
        consumers_part = ""
        for proxyuser in [
            *all_subscriptionperiods_obj_list,
            *all_nodeinternaluser_ob_list,
            *reverse_proxyusers,
            *tunn_all_users,
        ]:
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
                "config": proxy_manager_config,
                "node_obj": node_obj,
                "inbound_tag": inbound_tag,
                "consumers_part": consumers_part,
                **extra_ctx,
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
        if xray_inbound.strip():
            if inbound_parts:
                inbound_parts += ",\n"
            inbound_parts += xray_inbound

        if inbound.haproxy_backend:
            haproxy_backends_parts.append(
                django.template.Template(inbound.haproxy_backend).render(context=template_context)
            )
        if inbound.haproxy_matcher_80:
            haproxy_80_matchers_parts.append(
                django.template.Template(inbound.haproxy_matcher_80).render(context=template_context)
            )
        if inbound.haproxy_matcher_443:
            haproxy_443_matchers_parts.append(
                django.template.Template(inbound.haproxy_matcher_443).render(context=template_context)
            )
        if inbound.nginx_path_config:
            nginx_path_matchers_parts.append(
                django.template.Template(inbound.nginx_path_config).render(context=template_context)
            )

    template_context = node_manager_services.NodeTemplateContext(
        {
            "node": node_obj,
            "inbound_parts": inbound_parts,
            "rule_parts": rule_parts,
            "outbound_parts": list(all_xray_outbounds.values()),
            "outbound_tags": list(all_xray_outbounds.keys()),
            "balancer_parts": all_balancer_parts,
            "bridge_parts": ",\n".join([json.dumps(i, indent=4) for i in xray_bridges]),
            "portal_parts": ",\n".join([json.dumps(i, indent=4) for i in xray_portals]),
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
            node_manager_services.HAPROXY_KEY: {
                "backends_parts": haproxy_backends_parts,
                "80_matchers_parts": haproxy_80_matchers_parts,
                "443_matchers_parts": haproxy_443_matchers_parts,
            },
            node_manager_services.NGINX_KEY: {"path_matchers_parts": nginx_path_matchers_parts},
        },
    )


class Balancer(Protocol):
    strategy_template: str | None
    max_rtt: int | None
    baselines: list[int] | None


def get_strategy_part(
    balancer_members: list[typing.BalancerMemberType], balancer_obj: Balancer | None
) -> tuple[str, str]:
    if balancer_obj is not None and balancer_obj.strategy_template:
        strategy_template = balancer_obj.strategy_template
    else:
        strategy_template = '{"type": "random"}'
    weight_summation = sum([i["weight"] for i in balancer_members])
    costs_part = ", ".join(
        [
            '{{"match": "{tag}", "value": {val}}}'.format(
                tag=balancer_member["tag"],
                val=max(
                    Decimal(weight_summation / balancer_member["weight"]).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_DOWN
                    ),
                    Decimal(0.01),
                ),
            )
            for balancer_member in balancer_members
        ]
    )
    strategy_part = django.template.Template(strategy_template).render(
        django.template.Context(
            {
                "costs_part": costs_part,
                "node_count": max(1, int(0.4 * len(balancer_members))),
                "max_rtt": balancer_obj.max_rtt,
                "baselines": balancer_obj.baselines,
            }
        )
    )
    # todo do a proper fallbacktag
    sorted_balancer_members = sorted(balancer_members, key=lambda x: x["weight"], reverse=True)
    first_weight = None
    r = []
    for i in sorted_balancer_members:
        if first_weight is None:
            first_weight = i["weight"]
            r.append(i)
        elif first_weight == i["weight"]:
            r.append(i)
        else:
            break

    return strategy_part, random.choice(r)["tag"]


class XrayOutBound:
    @staticmethod
    def get_node_outbound_name(*, connection_rule: models.ConnectionRule, nodeoutbound: models.ConnectionRuleOutbound):
        assert not nodeoutbound.is_reverse
        to_inbound_type = nodeoutbound.connector.outbound_type.to_inbound_type
        return f"{connection_rule.id}_{to_inbound_type.name if to_inbound_type else ''}_{nodeoutbound.id}"

    @staticmethod
    def get_node_tunn_outbound_name(
        *, connectiontunnel: models.ConnectionTunnel, outbound: models.ConnectionTunnelOutbound
    ):
        assert not outbound.is_reverse
        to_inbound_type = outbound.connector.outbound_type.to_inbound_type
        return f"tunn_{connectiontunnel.id}_{to_inbound_type.name if to_inbound_type else ''}_{outbound.id}"

    @staticmethod
    def get_node_outbound_balancer_allocation_idf(tag: str) -> str:
        return tag.split("_")[-1]

    @staticmethod
    def get_bridge_outbound_name(
        *,
        connection_rule: models.ConnectionRule,
        bridge_nodeoutbound: models.ConnectionRuleOutbound,
        balancer_allocation_idf: str,
    ):
        assert bridge_nodeoutbound.is_reverse
        to_inbound_type = bridge_nodeoutbound.connector.outbound_type.to_inbound_type
        bridge_tag = f"{connection_rule.id}_{to_inbound_type.name if to_inbound_type else ''}_{bridge_nodeoutbound.id}_{bridge_nodeoutbound.connector.dest_node_id}_{balancer_allocation_idf}"
        return bridge_tag, f"interconn-{bridge_tag}"

    @staticmethod
    def get_tunn_bridge_outbound_name(
        *, connectiontunnel: models.ConnectionTunnel, bridge_reverse: models.ConnectionTunnelOutbound
    ):
        assert bridge_reverse.is_reverse
        to_inbound_type = bridge_reverse.connector.outbound_type.to_inbound_type
        bridge_tag = f"tunn_{connectiontunnel.id}_{to_inbound_type.name if to_inbound_type else ''}_{bridge_reverse.id}_{bridge_reverse.tunnel.source_node_id}"
        return bridge_tag, f"interconn-{bridge_tag}"

    @staticmethod
    def get_portal_outbound_name(
        *,
        connection_rule: models.ConnectionRule,
        portal_nodeoutbound: models.ConnectionRuleOutbound,
        balancer_allocation_idf: str,
    ):
        assert portal_nodeoutbound.is_reverse
        to_inbound_type = portal_nodeoutbound.connector.outbound_type.to_inbound_type
        portal_tag = f"reverse-{connection_rule.id}_{to_inbound_type.name if to_inbound_type else ''}_{portal_nodeoutbound.id}_{portal_nodeoutbound.apply_node_id}_{balancer_allocation_idf}"
        return portal_tag

    @staticmethod
    def get_tunn_portal_outbound_name(
        *, connectiontunnel: models.ConnectionTunnel, portal_reverse: models.ConnectionTunnelOutbound
    ):
        assert portal_reverse.is_reverse
        to_inbound_type = portal_reverse.connector.outbound_type.to_inbound_type
        portal_tag = f"reverse-tunn_{connectiontunnel.id}_{to_inbound_type.name if to_inbound_type else ''}_{portal_reverse.id}_{portal_reverse.tunnel.dest_node_id}"
        return portal_tag

    @staticmethod
    def parse_outbound_name(
        node: node_manager_models.Node, name: str
    ) -> models.ConnectionRuleOutbound | models.ConnectionTunnelOutbound | None:
        node_outbound_pattern = r"interconn-(?P<connection_rule_id>\d+)_(?P<to_inbound_type_name>.*)_(?P<bridge_reverse_id>\d+)_(?P<portal_node_id>\d+)_(?P<allocation_name>.*)"
        match_res = re.search(node_outbound_pattern, name)
        if match_res and len(match_res.groups()) == 5:
            connection_rule_id = match_res.group("connection_rule_id")
            to_inbound_type_name = match_res.group("to_inbound_type_name")
            bridge_reverse_id = match_res.group("bridge_reverse_id")
            portal_node_id = match_res.group("portal_node_id")
            allocation_name = match_res.group("allocation_name")

            reverse_obj = (
                models.ConnectionRuleOutbound.objects.filter(
                    apply_node=node,
                    rule_id=connection_rule_id,
                    connector__dest_node_id=portal_node_id,
                    id=bridge_reverse_id,
                )
                .select_related("connector__outbound_type", "connector__dest_node", "apply_node")
                .first()
            )
            return reverse_obj
        node_outbound_pattern = r"interconn-tunn_(?P<connectiontunnel_id>\d+)_(?P<to_inbound_type_name>.*)_(?P<bridge_reverse_id>\d+)_(?P<source_node_id>\d+)"
        match_res = re.search(node_outbound_pattern, name)
        if match_res and len(match_res.groups()) == 4:
            connectiontunnel_id = match_res.group("connectiontunnel_id")
            to_inbound_type_name = match_res.group("to_inbound_type_name")
            bridge_reverse_id = match_res.group("bridge_reverse_id")
            source_node_id = match_res.group("source_node_id")

            reverse_obj = (
                models.ConnectionTunnelOutbound.objects.filter(
                    tunnel__dest_node=node,
                    tunnel_id=connectiontunnel_id,
                    tunnel__source_node_id=source_node_id,
                    id=bridge_reverse_id,
                )
                .select_related("connector__outbound_type", "connector__dest_node")
                .first()
            )
            return reverse_obj
        node_outbound_pattern = r"reverse-(?P<connection_rule_id>\d+)_(?P<to_inbound_type_name>.*)_(?P<portal_reverse_id>\d+)_(?P<bridge_node_id>\d+)_(?P<allocation_name>.*)"
        match_res = re.search(node_outbound_pattern, name)
        if match_res and len(match_res.groups()) == 5:
            connection_rule_id = match_res.group("connection_rule_id")
            to_inbound_type_name = match_res.group("to_inbound_type_name")
            portal_reverse_id = match_res.group("portal_reverse_id")
            bridge_node_id = match_res.group("bridge_node_id")
            allocation_name = match_res.group("allocation_name")

            reverse_obj = (
                models.ConnectionRuleOutbound.objects.filter(
                    apply_node_id=bridge_node_id,
                    rule_id=connection_rule_id,
                    connector__dest_node=node,
                    id=portal_reverse_id,
                )
                .select_related("connector__outbound_type", "connector__dest_node", "apply_node")
                .first()
            )
            return reverse_obj
        node_outbound_pattern = r"reverse-tunn_(?P<connectiontunnel_id>\d+)_(?P<to_inbound_type_name>.*)_(?P<portal_reverse_id>\d+)_(?P<dest_node_id>\d+)"
        match_res = re.search(node_outbound_pattern, name)
        if match_res and len(match_res.groups()) == 4:
            connectiontunnel_id = match_res.group("connectiontunnel_id")
            to_inbound_type_name = match_res.group("to_inbound_type_name")
            portal_reverse_id = match_res.group("portal_reverse_id")
            dest_node_id = match_res.group("dest_node_id")

            reverse_obj = (
                models.ConnectionTunnelOutbound.objects.filter(
                    tunnel__source_node=node,
                    tunnel_id=connectiontunnel_id,
                    tunnel__dest_node_id=dest_node_id,
                    id=portal_reverse_id,
                )
                .select_related("connector__outbound_type", "connector__dest_node")
                .first()
            )
            return reverse_obj
        node_outbound_pattern = (
            r"tunn_(?P<connectiontunnel_id>\d+)_(?P<to_inbound_type_name>.*)_(?P<connectiontunneloutbound_id>\d+)"
        )
        match_res = re.search(node_outbound_pattern, name)
        if match_res and len(match_res.groups()) == 3:
            connectiontunnel_id = match_res.group("connectiontunnel_id")
            to_inbound_type_name = match_res.group("to_inbound_type_name")
            connectiontunneloutbound_id = match_res.group("connectiontunneloutbound_id")

            nodeoutbound_obj = (
                models.ConnectionTunnelOutbound.objects.filter(
                    tunnel__source_node=node, tunnel_id=connectiontunnel_id, id=connectiontunneloutbound_id
                )
                .select_related("connector__outbound_type", "connector__dest_node")
                .first()
            )
            return nodeoutbound_obj

        node_outbound_pattern = (
            r"(?P<connection_rule_id>\d+)_(?P<to_inbound_type_name>.*)_(?P<connectionruleoutbound_id>\d+)"
        )
        match_res = re.search(node_outbound_pattern, name)
        if match_res and len(match_res.groups()) == 3:
            connection_rule_id = match_res.group("connection_rule_id")
            to_inbound_type_name = match_res.group("to_inbound_type_name")
            connectionruleoutbound_id = match_res.group("connectionruleoutbound_id")

            nodeoutbound_obj = (
                models.ConnectionRuleOutbound.objects.filter(
                    apply_node=node, rule_id=connection_rule_id, id=connectionruleoutbound_id
                )
                .select_related("connector__outbound_type", "connector__dest_node", "apply_node")
                .first()
            )
            return nodeoutbound_obj
