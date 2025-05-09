import datetime
import ipaddress
import json
import logging
import pathlib
import random
import re
import tomllib
import zoneinfo
from collections import defaultdict
from datetime import timedelta
from hashlib import sha256

from asgiref.sync import sync_to_async

import django.template
from bigO.core import models as core_models
from bigO.proxy_manager import services as services_models
from config import settings
from django.db import transaction
from django.db.models import Subquery
from django.http import HttpHeaders
from django.urls import reverse
from django.utils import timezone

from . import models, tasks, typing
from .typing import FileSchema

logger = logging.getLogger(__name__)


def node_spec_create(*, node: models.Node, ip_a: str):
    """
    makes decisions based on the node current state(spec)
    """
    if container_spec := node.container_spec:
        if ipv4_extractor := node.container_spec.ip_a_container_ipv4_extractor:
            res = ipv4_extractor.extract(ip_a)
            if res is None:
                logger.critical(f"cannot find container ipv4 for {node=}")
                container_spec.ipv4 = None
            else:
                container_spec.ipv4 = res
        if ipv6_extractor := node.container_spec.ip_a_container_ipv6_extractor:
            res = ipv6_extractor.extract(ip_a)
            if res is None:
                logger.critical(f"cannot find container ipv6 for {node=}")
                container_spec.ipv6 = None
            else:
                container_spec.ipv6 = res
        container_spec.save()


def node_process_stats(
    node_obj: models.Node,
    configs_states: list[typing.ConfigStateSchema] | None,
    smallo1_logs: typing.SupervisorProcessTailLogSerializerSchema | None = None,
    smallo2_logs: typing.SupervisorProcessTailLogSerializerSchema | None = None,
):
    streams: list[typing.LokiStram] = []
    configs_states = configs_states or []
    base_labels = {"service_name": "bigo", "node_id": node_obj.id, "node_name": node_obj.name}
    for i in configs_states:
        service_name = i.supervisorprocessinfo.name
        send_stdout = False
        send_stderr = False
        if service_name.startswith("custom_"):
            ___, cc_id, *___ = service_name.split("_")
            try:
                nodecustomconfig_obj = models.NodeCustomConfig.objects.get(node=node_obj, custom_config_id=cc_id)
            except models.NodeCustomConfig.DoesNotExist:
                logger.info(f"node service name {service_name} not found for node_process_stats")
                continue
            send_stdout = nodecustomconfig_obj.stdout_action_type == core_models.LogActionType.TO_LOKI
            send_stderr = nodecustomconfig_obj.stderr_action_type == core_models.LogActionType.TO_LOKI
        elif service_name.startswith("eati_"):
            ___, etn_id = service_name.split("_")
            try:
                easytiernode_obj = models.EasyTierNode.objects.get(id=etn_id)
                send_stdout = easytiernode_obj.stdout_action_type == core_models.LogActionType.TO_LOKI
                send_stderr = easytiernode_obj.stderr_action_type == core_models.LogActionType.TO_LOKI
            except models.EasyTierNode.DoesNotExist:
                logger.info(f"node service name {service_name} not found for node_process_stats")
                continue
        elif service_name == "global_nginx_conf":
            continue
        elif (
            node_obj.collect_metrics
            and service_name == "telegraf_conf"
            and i.stdout.bytes
            and getattr(settings, "INFLUX_URL", False)
        ):
            tasks.telegraf_to_influx_send.delay(telegraf_json_lines=i.stdout.bytes, base_labels=base_labels)
        elif service_name == "goingto_conf" and i.stdout.bytes and getattr(settings, "INFLUX_URL", False):
            handle_goingto = tasks.handle_goingto if settings.DEBUG else tasks.handle_goingto.delay
            handle_goingto(node_obj.id, goingto_json_lines=i.stdout.bytes, base_labels=base_labels)
        if node_obj.collect_logs and getattr(settings, "LOKI_PUSH_ENDPOINT", False):
            collected_at = i.time
            if send_stderr and i.stderr.bytes:
                stderr_lines = i.stderr.bytes.split("\n")
                stream = {
                    **base_labels,
                    "config_name": i.supervisorprocessinfo.name,
                    "captured_at": "stderr",
                }
                values = []
                for stderr_line in stderr_lines:
                    values.append([str(int(collected_at.timestamp() * 1e9)), stderr_line])
                streams.append({"stream": stream, "values": values})
            if send_stdout and i.stdout.bytes:
                stdout_lines = i.stdout.bytes.split("\n")
                stream = {
                    **base_labels,
                    "config_name": i.supervisorprocessinfo.name,
                    "captured_at": "stdout",
                }
                values = []
                for stdout_line in stdout_lines:
                    values.append([str(int(collected_at.timestamp() * 1e9)), stdout_line])
                streams.append({"stream": stream, "values": values})
    if node_obj.collect_logs and getattr(settings, "LOKI_PUSH_ENDPOINT", False):
        if smallo1_logs and smallo1_logs.bytes:
            logtime_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}"
            smallo1_log_lines = smallo1_logs.bytes.split("\n")
            stream = {**base_labels, "config_name": "smallo1"}
            values = []
            for smallo1_log_line in smallo1_log_lines:
                if not smallo1_log_line:
                    continue  # skip blank lines
                logtime_match = re.search(logtime_pattern, smallo1_log_line)
                if logtime_match:
                    logtime_str = logtime_match.group()
                    logged_at = datetime.datetime.strptime(logtime_str, "%Y-%m-%d %H:%M:%S,%f").replace(
                        tzinfo=zoneinfo.ZoneInfo("UTC")
                    )
                else:
                    logger.error(f"cannot match logtime from log line of smallo1 of {node_obj=}; {smallo1_log_line=}")
                    continue
                values.append([str(int(logged_at.timestamp() * 1e9)), smallo1_log_line])
            streams.append({"stream": stream, "values": values})
        tasks.send_to_loki.delay(streams=streams)


def get_easytier_to_node_ips(*, source_node: models.Node, dest_node_id: int) -> list[ipaddress.IPv4Address]:
    source_ea_networks = models.EasyTierNetwork.objects.filter(network_easytiernodes__node_id=source_node.id)
    dest_ea_nodes = models.EasyTierNode.objects.filter(
        node_id=dest_node_id, network_id__in=Subquery(source_ea_networks.values("id"))
    )
    dest_node = models.Node.objects.get(id=dest_node_id)
    res = []
    for i in dest_ea_nodes:
        if i.ipv4:
            res.append(i.ipv4)
        elif i.node.container_spec and i.node.container_spec.ipv4:
            res.append(i.node.container_spec.ipv4)
        else:
            logger.warning(f"no easytier destination from {source_node=} to {dest_node=}")
    return res


def create_node_sync_stat(request_headers: HttpHeaders, node: models.Node) -> models.NodeLatestSyncStat:
    try:
        obj = models.NodeLatestSyncStat.objects.get(node=node)
    except models.NodeLatestSyncStat.DoesNotExist:
        obj = models.NodeLatestSyncStat(node=node)
    obj.request_headers = json.dumps(dict(request_headers))
    obj.initiated_at = timezone.now()
    obj.agent_spec = request_headers.get("user-agent", "")[:200]
    obj.response_payload = None
    obj.respond_at = None
    if obj.pk:
        count_up_to_now = obj.count_up_to_now + 1
    else:
        count_up_to_now = 1
    obj.count_up_to_now = count_up_to_now

    obj.save()
    return obj


def complete_node_sync_stat(obj: models.NodeLatestSyncStat, response_payload) -> None:
    obj.response_payload = json.dumps(response_payload)
    obj.respond_at = timezone.now()

    obj.save()


def create_default_cert_for_node(node: models.Node) -> core_models.Certificate:
    from cryptography import x509
    from cryptography.hazmat._oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    config = core_models.SiteConfiguration.objects.get()
    ca_cert = config.nodes_ca_cert
    cert_slug = f"node_{node.pk}_defualt"

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key_content = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    privatekey_obj = core_models.PrivateKey()
    privatekey_obj.algorithm = core_models.PrivateKey.AlgorithmChoices.RSA
    privatekey_obj.content = private_key_content.decode("utf-8")
    privatekey_obj.slug = cert_slug
    privatekey_obj.key_length = private_key.key_size

    common_name = f"*.{node.name}.com"
    valid_after = timezone.now() - timedelta(days=random.randint(1, 365))
    valid_before = timezone.now() + timedelta(days=3650)
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "My Organization"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(subject)
        .sign(private_key=private_key, algorithm=hashes.SHA256())
    )
    parent_certificate = x509.load_pem_x509_certificate(ca_cert.content.encode("utf-8"))
    parent_private_key = serialization.load_pem_private_key(
        ca_cert.private_key.content.encode("utf-8"),
        password=None,
    )
    certificate = (
        x509.CertificateBuilder()
        .subject_name(csr.subject)
        .issuer_name(parent_certificate.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(valid_after)
        .not_valid_after(valid_before)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(common_name)]),
            critical=False,
        )
        .sign(private_key=parent_private_key, algorithm=hashes.SHA256())
    )
    certificate_content = certificate.public_bytes(serialization.Encoding.PEM)
    certificate_obj = core_models.Certificate()
    certificate_obj.is_ca = False
    certificate_obj.private_key = privatekey_obj
    certificate_obj.slug = cert_slug
    certificate_obj.content = certificate_content.decode("utf-8")
    certificate_obj.fingerprint = certificate.fingerprint(hashes.SHA256()).hex()
    certificate_obj.algorithm = core_models.Certificate.AlgorithmChoices.RSA
    certificate_obj.parent_certificate = ca_cert
    certificate_obj.valid_from = valid_after
    certificate_obj.valid_to = valid_before

    with transaction.atomic(using="main"):
        privatekey_obj.save()
        certificate_obj.save()
    return certificate_obj


def get_global_haproxy_conf_v2(
    node_obj,
    xray_backends_parts: list,
    xray_80_matchers_parts: list,
    xray_443_matchers_parts: list,
    node_work_dir: pathlib.Path,
    base_url: str,
) -> tuple[str, list[typing.FileSchema]] | None:
    site_config: core_models.SiteConfiguration = core_models.SiteConfiguration.objects.get()
    if site_config.main_haproxy is None:
        logger.critical("no program set for global_haproxy_conf")
        return None
    haproxy_program = site_config.main_haproxy.get_program_for_node(node_obj)
    if haproxy_program is None:
        raise ProgramNotFound(program_version=site_config.main_haproxy)
    elif isinstance(haproxy_program, models.ProgramBinary):
        dest_path = node_work_dir.joinpath("bin", f"{haproxy_program.id}_{haproxy_program.hash[:6]}")
        haproxy_program_file = typing.FileSchema(
            dest_path=dest_path,
            url=base_url + reverse("node_manager:node_program_binary_content_by_hash", args=[haproxy_program.hash]),
            permission=all_permission,
            hash=haproxy_program.hash,
        )
    elif isinstance(haproxy_program, models.NodeInnerProgram):
        haproxy_program_file = typing.FileSchema(
            dest_path=haproxy_program.path,
            permission=all_permission,
        )
    else:
        raise AssertionError
    files = []
    files.append(haproxy_program_file)

    xray_backends_part = "\n".join(xray_backends_parts)
    xray_80_matchers_part = "\n".join(xray_80_matchers_parts)
    xray_443_matchers_part = "\n".join(xray_443_matchers_parts)

    template_context = NodeTemplateContext(
        {
            "node_obj": node_obj,
            "xray_backends_part": xray_backends_part,
            "xray_80_matchers_part": xray_80_matchers_part,
            "xray_443_matchers_part": xray_443_matchers_part,
        },
        node_work_dir=node_work_dir,
        base_url=base_url,
    )
    haproxy_config_content = django.template.Template(
        """
{% load node_manager %}
global
    log /dev/log local0
    # limited-quic

defaults
    log global
    retry-on all-retryable-errors

    timeout connect 5s
    timeout client 50s
    timeout client-fin 50s
    timeout server 50s
    timeout tunnel 1h
    default-server init-addr none
    default-server inter 15s fastinter 2s downinter 5s rise 3 fall 3
    mode tcp

frontend https-in
    bind :443,:::443 v4v6 tfo
    # option tcplog
    # option dontlognull
    tcp-request inspect-delay 5s
    tcp-request content accept if { req.ssl_hello_type 1 }

    {{ xray_443_matchers_part }}

    default_backend to_https_in_ssl

backend to_https_in_ssl
    server haproxy abns@https_in_ssl send-proxy-v2 tfo

frontend http-https-in
    bind :80,:::80 v4v6 tfo

    {% allowed_valid_certs node=node_obj pem='True' as certs %}
    bind abns@https_in_ssl tfo accept-proxy ssl {% for i in certs %}crt {{ i }} {% endfor %}alpn h2,http/1.1,h3 allow-0rtt
    acl h2 ssl_fc_alpn -i h2
    #acl h2 ssl_fc_npn -i h2

    http-response set-header alt-svc "h3=\":443\";ma=900;"
    tcp-request inspect-delay 5s
    tcp-request content accept if HTTP

    # use_backend vlesshs if { path_beg /TWJesFY44i6zOOD8pYMb }
    # use_backend vlessw if { path_beg /13wuO5tMdxJDeSHexv5DKmT0 }
    {{ xray_80_matchers_part }}

    use_backend nginx_dispatcher_h2 if h2
    default_backend nginx_dispatcher

# this server handles xray http2 proxies
backend nginx_dispatcher_h2
    server nginx unix@/run/nginx_xray_h2.sock send-proxy-v2 tfo

# this server doesn't handle any proxy
backend nginx_dispatcher
    server nginx unix@/run/nginx_xray_h1.sock send-proxy-v2


# backend vlesshs
#   #mode http
#   #server vlesshs abns@vless-xhttp send-proxy-v2
#   #server vlesshs 127.0.0.1:1025
#   server vlesshs unix@/var/run/vless-xhttp.sock
# backend vlessw
#   server vlessw abns@h2_vless_ws_new send-proxy-v2 tfo
{{ xray_backends_part }}
"""
    ).render(context=template_context)

    haproxy_config_content_hash = sha256(haproxy_config_content.encode("utf-8")).hexdigest()
    haproxy_config_content_file = typing.FileSchema(
        dest_path=node_work_dir.joinpath("conf", f"haproxy_{haproxy_config_content_hash[:6]}"),
        content=haproxy_config_content,
        hash=haproxy_config_content_hash,
        permission=all_permission,
    )
    files.append(haproxy_config_content_file)
    new_files = get_configdependentcontents_from_context(template_context)
    files.extend(new_files)

    supervisor_config = f"""
# config={timezone.now()}
[program:global_haproxy_conf]
command={haproxy_program_file.dest_path} -f {haproxy_config_content_file.dest_path} -d
autostart=true
autorestart=true
priority=10
"""
    return supervisor_config, files


def get_global_nginx_conf_v1(node: models.Node) -> tuple[str, str, dict] | None:
    usage = False
    deps = {}
    http_part = ""
    stream_part = ""

    supervisor_nginx_conf = get_supervisor_nginx_conf_v1(node=node)
    if supervisor_nginx_conf:
        http_part += supervisor_nginx_conf[0]
        deps = supervisor_nginx_conf[1]
        usage = True
    proxy_manager_nginx_conf = services_models.get_proxy_manager_nginx_conf_v1(node_obj=node)
    if proxy_manager_nginx_conf and (proxy_manager_nginx_conf[0] or proxy_manager_nginx_conf[1]):
        http_part += proxy_manager_nginx_conf[0]
        stream_part += proxy_manager_nginx_conf[1]
        deps = proxy_manager_nginx_conf[2]
        usage = True

    if not usage:
        return None

    res = django.template.Template(
        """
user root;
include /etc/nginx/modules-enabled/*.conf;
worker_processes  auto;

events {
    worker_connections  1024;
}
stream {
    {{ stream|safe }}
    log_format dns '$remote_addr - - [$time_local] $protocol $status $bytes_sent $bytes_received $session_time "$upstream_addr"';

    error_log stderr warn;
    access_log /dev/stdout dns;
}
http {
    {{ http|safe }}
    error_log stderr warn;
    access_log /dev/stdout;
}
    """
    ).render(django.template.Context({"stream": stream_part, "http": http_part}))

    run_opt = django.template.Template('-c *#path:main#* -g "daemon off;"').render(context=django.template.Context({}))
    return run_opt, res, deps


def get_global_nginx_conf_v2(
    node_obj,
    xray_path_matchers_parts: list,
    node_work_dir: pathlib.Path,
    base_url: str,
) -> tuple[str, list[typing.FileSchema]] | None:
    site_config: core_models.SiteConfiguration = core_models.SiteConfiguration.objects.get()
    if site_config.main_nginx is None:
        logger.critical("no program set for global_nginc_conf")
        return None
    nginx_program = site_config.main_nginx.get_program_for_node(node_obj)
    if nginx_program is None:
        raise ProgramNotFound(program_version=site_config.main_nginx)
    elif isinstance(nginx_program, models.ProgramBinary):
        dest_path = node_work_dir.joinpath("bin", f"{nginx_program.id}_{nginx_program.hash[:6]}")
        nginx_program_file = typing.FileSchema(
            dest_path=dest_path,
            url=base_url + reverse("node_manager:node_program_binary_content_by_hash", args=[nginx_program.hash]),
            permission=all_permission,
            hash=nginx_program.hash,
        )
    elif isinstance(nginx_program, models.NodeInnerProgram):
        nginx_program_file = typing.FileSchema(
            dest_path=nginx_program.path,
            permission=all_permission,
        )
    else:
        raise AssertionError
    files = []
    files.append(nginx_program_file)

    usage = False
    http_part = ""
    stream_part = ""

    supervisor_nginx_conf = get_supervisor_nginx_conf_v2(
        node_obj=node_obj, node_work_dir=node_work_dir, base_url=base_url
    )
    if supervisor_nginx_conf:
        http_part += supervisor_nginx_conf[0].content
        new_files = supervisor_nginx_conf[1]
        files.extend(new_files)
        usage = True
    proxy_manager_nginx_conf = services_models.get_proxy_manager_nginx_conf_v2(
        node_obj=node_obj,
        xray_path_matchers_parts=xray_path_matchers_parts,
        node_work_dir=node_work_dir,
        base_url=base_url,
    )
    if proxy_manager_nginx_conf and (proxy_manager_nginx_conf[0] or proxy_manager_nginx_conf[1]):
        http_part += proxy_manager_nginx_conf[0]
        stream_part += proxy_manager_nginx_conf[1]
        new_files = proxy_manager_nginx_conf[2]
        files.extend(new_files)
        usage = True

    if not usage:
        return None
    template_context = NodeTemplateContext(
        {"stream": stream_part, "http": http_part}, node_work_dir=node_work_dir, base_url=base_url
    )
    config_content = django.template.Template(
        """
user root;
include /etc/nginx/modules-enabled/*.conf;
worker_processes  auto;

events {
    worker_connections  1024;
}
stream {
    {{ stream|safe }}
    log_format dns '$remote_addr - - [$time_local] $protocol $status $bytes_sent $bytes_received $session_time "$upstream_addr"';

    error_log stderr warn;
    access_log /dev/stdout dns;
}
http {
    {{ http|safe }}
    error_log stderr warn;
    access_log /dev/stdout;
}
    """
    ).render(template_context)
    config_content_hash = sha256(config_content.encode("utf-8")).hexdigest()
    config_content_file = typing.FileSchema(
        dest_path=node_work_dir.joinpath("conf", f"nginx_supervisor_part_{config_content_hash[:6]}"),
        content=config_content,
        hash=config_content_hash,
        permission=all_permission,
    )
    files.append(config_content_file)
    new_files = get_configdependentcontents_from_context(template_context)
    files.extend(new_files)

    supervisor_config = f"""
# config={timezone.now()}
[program:global_nginx_conf]
command={nginx_program_file.dest_path} -c {config_content_file.dest_path} -g "daemon off;"
autostart=true
autorestart=true
priority=10
    """
    return supervisor_config, files


def get_supervisor_nginx_conf_v1(node: models.Node) -> tuple[str, dict] | None:
    nodesupervisorconfig_obj: models.NodeSupervisorConfig | None = models.NodeSupervisorConfig.objects.filter(
        node=node
    ).first()
    if nodesupervisorconfig_obj is None or nodesupervisorconfig_obj.xml_rpc_api_expose_port is None:
        return None
    context = {
        "servername": f"supervisor.{node.name}.com",
        "supervisor_xml_rpc_api_expose_port": nodesupervisorconfig_obj.xml_rpc_api_expose_port,
        "node": node,
    }
    context = django.template.Context(context)
    cnfg = """
{% load node_manager %}
upstream supervisor {
    server  unix:/var/run/supervisor.sock;
    keepalive 2;
}
server {
    listen {{ supervisor_xml_rpc_api_expose_port }} ssl http2;
    listen [::]:{{ supervisor_xml_rpc_api_expose_port }} ssl http2;
    server_name  {{ servername }};
    ssl_certificate {% default_cert node %};
    ssl_certificate_key {% default_cert_key node %};
    ssl_protocols TLSv1.3;
    location / {
        auth_basic           "closed site";
        auth_basic_user_file {% default_basic_http_file node %};

        proxy_pass http://supervisor;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_http_version 1.1;
        proxy_set_header Connection 'upgrade';
    }
}
    """
    result = django.template.Template(cnfg).render(context=django.template.Context(context))
    return result, context.get("deps", {"globals": []})


def get_supervisor_nginx_conf_v2(
    node_obj, node_work_dir: pathlib.Path, base_url: str
) -> tuple[typing.FileSchema, list[typing.FileSchema]] | None:
    nodesupervisorconfig_obj: models.NodeSupervisorConfig | None = models.NodeSupervisorConfig.objects.filter(
        node=node_obj
    ).first()
    if nodesupervisorconfig_obj is None or nodesupervisorconfig_obj.xml_rpc_api_expose_port is None:
        return None
    template_context = NodeTemplateContext(
        {
            "servername": f"supervisor.{node_obj.name}.com",
            "supervisor_xml_rpc_api_expose_port": nodesupervisorconfig_obj.xml_rpc_api_expose_port,
            "node": node_obj,
        },
        node_work_dir=node_work_dir,
        base_url=base_url,
    )
    cnfg = """
{% load node_manager %}
upstream supervisor {
    server  unix:/var/run/supervisor.sock;
    keepalive 2;
}
server {
    listen {{ supervisor_xml_rpc_api_expose_port }} ssl http2;
    listen [::]:{{ supervisor_xml_rpc_api_expose_port }} ssl http2;
    server_name  {{ servername }};
    ssl_certificate {% default_cert node %};
    ssl_certificate_key {% default_cert_key node %};
    ssl_protocols TLSv1.3;
    location / {
        auth_basic           "closed site";
        auth_basic_user_file {% default_basic_http_file node %};

        proxy_pass http://supervisor;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_http_version 1.1;
        proxy_set_header Connection 'upgrade';
    }
}
    """
    cnfg_content = django.template.Template(cnfg).render(context=template_context)
    cnfg_content_hash = sha256(cnfg_content.encode("utf-8")).hexdigest()

    cnfg_content_file = typing.FileSchema(
        dest_path=f"nginx_supervisor_part_{cnfg_content_hash[:6]}",
        content=cnfg_content,
        hash=cnfg_content_hash,
        permission=all_permission,
    )

    new_files = get_configdependentcontents_from_context(template_context)
    files = new_files

    return cnfg_content_file, files


def get_telegraf_conf(node: models.Node) -> str | None:
    if not node.collect_metrics:
        return None
    context = {}
    context = django.template.Context(context)
    cnfg = """
[agent]
  round_interval = true
  metric_batch_size = 1000
  metric_buffer_limit = 10000
  collection_jitter = "0s"
  flush_interval = "10s"
  flush_jitter = "0s"
  precision = "0s"

[[outputs.file]]
  files = ["stdout"]
  data_format = "json"
  use_batch_format = true
  json_timestamp_units = "1s"

[[inputs.mem]]
[[inputs.processes]]
  use_sudo = true
[[inputs.swap]]
[[inputs.system]]
[[inputs.net]]
    """
    result = django.template.Template(cnfg).render(context=django.template.Context(context))
    run_opt = django.template.Template("-config *#path:main#*").render(context=context)
    return run_opt, result, context.get("deps", {"globals": []})


### o2 style


class IncorrectTemplateFormat(Exception):
    pass


class ProgramNotFound(Exception):
    def __init__(self, *args, program_version: models.ProgramVersion, **kwargs):
        super().__init__(*args, **kwargs)
        self.program_version = program_version


def get_configdependentcontents_from_context(context: django.template.Context) -> list[FileSchema]:
    return context.get("deps", {}).get("dependents", [])


def add_configdependentcontent_to_context(context: django.template.Context, configdependentcontent: typing.FileSchema):
    deps = context.get("deps", {"dependents": []})
    deps["dependents"].append(configdependentcontent)
    context["deps"] = deps


def get_deps(template: str) -> list[tuple[str, str]]:
    matches = re.findall(r"\*#(\w+):(\w+)#\*", template)
    return matches


def render_deps(template: str, deps: set[str], proccessed_dependantfiles_map: dict[str, FileSchema]):
    for dep in deps:
        template = template.replace(f"*#path:{dep}#*", str(proccessed_dependantfiles_map[dep].dest_path))
    return template


def get_customconfig_proccessname(customconfig: models.CustomConfig):
    return f"custom_{customconfig.id}"


all_permission = int("744", 8)


class NodeTemplateContext(django.template.Context):
    def __init__(self, *args, node_work_dir: pathlib.Path, base_url: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.node_work_dir = node_work_dir
        self.base_url = base_url


async def get_custom(
    node: models.Node, customconfig: models.CustomConfig, node_work_dir: pathlib.Path, base_url: str
) -> tuple[str, list[FileSchema]]:
    files = []
    unproccessed_dependantfiles_map: dict[str, models.CustomConfigDependantFile] = {}
    proccessed_dependantfiles_map = {}
    template_context = NodeTemplateContext(
        {
            "node_obj": node,
        },
        node_work_dir=node_work_dir,
        base_url=base_url,
    )
    async for dependantfile in customconfig.dependantfiles.all().select_related("file"):
        if dependantfile.template:
            template = django.template.Template("{% load node_manager %}" + dependantfile.template)
            rendered_template = template.render(context=template_context)
            dependantfile.rendered_template = rendered_template
            unproccessed_dependantfiles_map[dependantfile.key] = dependantfile
        elif dependantfile.file:
            file = await sync_to_async(dependantfile.file.get_program_for_node)(node)
            if file is None:
                raise ProgramNotFound(program_version=dependantfile.file)
            elif isinstance(file, models.ProgramBinary):
                dest_path = node_work_dir.joinpath("bin", f"{file.program_version_id}_{file.hash[:6]}")
                url = base_url + reverse("node_manager:node_program_binary_content_by_hash", args=[file.hash])
                proccessed_dependantfiles_map[dependantfile.key] = FileSchema(
                    dest_path=dest_path, url=url, permission=all_permission, hash=file.hash
                )
            elif isinstance(file, models.NodeInnerProgram):
                dest_path = file.path
                proccessed_dependantfiles_map[dependantfile.key] = FileSchema(
                    dest_path=dest_path, pepermission=all_permission
                )
            else:
                raise AssertionError
        else:
            raise AssertionError

    dependantfiles_deps = defaultdict(set)
    for key, dependantfile in unproccessed_dependantfiles_map.items():
        deps = get_deps(dependantfile.rendered_template)
        for dep in deps:
            dependantfiles_deps[key].add(dep[1])

    while unproccessed_dependantfiles_map:
        next_to_resolve_key = [
            key
            for key, dependantfile in unproccessed_dependantfiles_map.items()
            if not (dependantfiles_deps[key] - proccessed_dependantfiles_map.keys())
        ]
        if not next_to_resolve_key:
            raise AssertionError
        next_to_resolve_key = next_to_resolve_key[0]
        dependantfile = unproccessed_dependantfiles_map[next_to_resolve_key]
        deps = dependantfiles_deps[next_to_resolve_key]
        content = render_deps(dependantfile.rendered_template, deps, proccessed_dependantfiles_map)
        content_hash = sha256(content.encode("utf-8")).hexdigest()

        file_name = f"custom_{customconfig.id}_{content_hash[:6]}_{next_to_resolve_key}"
        if dependantfile.name_extension:
            file_name += dependantfile.name_extension
        dest_path = node_work_dir.joinpath("conf", file_name)
        proccessed_dependantfiles_map[next_to_resolve_key] = FileSchema(
            dest_path=dest_path, content=content, hash=content_hash, permission=all_permission
        )
        unproccessed_dependantfiles_map.pop(next_to_resolve_key)

    run_opts_template = django.template.Template("{% load node_manager %}" + customconfig.run_opts_template)
    run_opts_rendered_template = run_opts_template.render(context=template_context)
    run_opts_content = render_deps(
        run_opts_rendered_template, {i[1] for i in get_deps(run_opts_rendered_template)}, proccessed_dependantfiles_map
    )
    proccessname = get_customconfig_proccessname(customconfig)
    supervisor_config = f"""
# config={timezone.now()}
[program:{proccessname}]
command={run_opts_content}
autostart=true
autorestart=true
priority=10
"""
    additional_files = get_configdependentcontents_from_context(template_context)
    files.extend(additional_files)
    return supervisor_config, [*files, *proccessed_dependantfiles_map.values()]


async def get_easytier(
    easytiernode_obj: models.EasyTierNode, node_work_dir: pathlib.Path, base_url: str
) -> tuple[str, list[FileSchema]]:
    toml_config_content = await sync_to_async(easytiernode_obj.get_toml_config_content)()
    try:
        tomllib.loads(toml_config_content)
    except tomllib.TOMLDecodeError as e:
        raise IncorrectTemplateFormat(e)
    files = []
    toml_config_content_hash = sha256(toml_config_content.encode("utf-8")).hexdigest()
    files.append(
        FileSchema(
            dest_path=node_work_dir.joinpath(
                "conf", f"eati_{easytiernode_obj.id}_{toml_config_content_hash[:6]}.toml"
            ),
            content=toml_config_content,
            hash=toml_config_content_hash,
            permission=all_permission,
        )
    )
    program_version = (
        await sync_to_async(lambda: easytiernode_obj.preferred_program_version)()
        or await sync_to_async(lambda: easytiernode_obj.network.program_version)()
    )
    program = await sync_to_async(program_version.get_program_for_node)(easytiernode_obj.node)
    if program is None:
        raise ProgramNotFound(program_version=program_version)
    elif isinstance(program, models.ProgramBinary):
        easytier_program_file = FileSchema(
            dest_path=node_work_dir.joinpath("bin", f"{program.program_version_id}_{program.hash[:6]}"),
            url=base_url + reverse("node_manager:node_program_binary_content_by_hash", args=[program.hash]),
            permission=all_permission,
            hash=program.hash,
        )
    elif isinstance(program, models.NodeInnerProgram):
        easytier_program_file = FileSchema(
            dest_path=program.path,
            permission=all_permission,
        )
    else:
        raise AssertionError
    files.append(easytier_program_file)
    toml_config_content_hash = sha256(toml_config_content.encode("utf-8")).hexdigest()
    toml_config_dest_path = node_work_dir.joinpath(
        "conf", f"eati_{easytiernode_obj.id}_{toml_config_content_hash[:6]}"
    )
    conf_file = FileSchema(
        dest_path=toml_config_dest_path,
        content=toml_config_content,
        hash=toml_config_content_hash,
        permission=all_permission,
    )
    files.append(conf_file)
    run_opts = await sync_to_async(easytiernode_obj.get_run_opts)()
    run_opts = run_opts.replace("CONFIGFILEPATH", str(conf_file.dest_path))
    supervisor_config = f"""
# config={timezone.now()}
[program:eati_{easytiernode_obj.id}]
command={easytier_program_file.dest_path} {run_opts}
autostart=true
autorestart=true
priority=10
"""
    return supervisor_config, files


async def get_telegraf(
    node_obj: models.Node, node_work_dir: pathlib.Path, base_url: str
) -> tuple[str, list[FileSchema]] | None:
    site_config: core_models.SiteConfiguration = await core_models.SiteConfiguration.objects.select_related(
        "main_telegraf"
    ).aget()
    if not node_obj.collect_metrics:
        return None
    elif node_obj.collect_metrics and site_config.main_telegraf is None:
        logger.critical("no program found for telegraf_conf")
        return None
    files = []
    telegraf_program = await sync_to_async(site_config.main_telegraf.get_program_for_node)(node_obj)
    if telegraf_program is None:
        raise ProgramNotFound(program_version=site_config.main_telegraf)
    elif isinstance(telegraf_program, models.ProgramBinary):
        dest_path = node_work_dir.joinpath("bin", f"telegraf_{telegraf_program.id}_{telegraf_program.hash[:6]}")
        telegraf_program_file = FileSchema(
            dest_path=dest_path,
            url=base_url + reverse("node_manager:node_program_binary_content_by_hash", args=[telegraf_program.hash]),
            permission=all_permission,
            hash=telegraf_program.hash,
        )
    elif isinstance(telegraf_program, models.NodeInnerProgram):
        telegraf_program_file = FileSchema(
            dest_path=telegraf_program.path,
            permission=all_permission,
        )
    else:
        raise AssertionError
    files.append(telegraf_program_file)
    template_context = django.template.Context({})
    cnfg_template = """
[agent]
  round_interval = true
  metric_batch_size = 1000
  metric_buffer_limit = 10000
  collection_jitter = "0s"
  flush_interval = "10s"
  flush_jitter = "0s"
  precision = "0s"

[[outputs.file]]
  files = ["stdout"]
  data_format = "json"
  use_batch_format = true
  json_timestamp_units = "1s"

[[inputs.mem]]
[[inputs.processes]]
  use_sudo = true
[[inputs.swap]]
[[inputs.system]]
[[inputs.net]]
    """
    telegraf_conf_content = django.template.Template(cnfg_template).render(
        context=django.template.Context(template_context)
    )
    telegraf_conf_hash = sha256(telegraf_conf_content.encode("utf-8")).hexdigest()
    telegraf_conf_content = FileSchema(
        dest_path=node_work_dir.joinpath("conf", f"telegraf_{telegraf_conf_hash[:6]}"),
        content=telegraf_conf_content,
        hash=telegraf_conf_hash,
        permission=all_permission,
    )
    files.append(telegraf_conf_content)
    supervisor_config = f"""
# config={timezone.now()}
[program:telegraf_conf]
command={telegraf_program_file.dest_path} -config {telegraf_conf_content.dest_path}
autostart=true
autorestart=true
priority=10
"""
    return supervisor_config, files


async def get_goingto_conf(
    node_obj: models.Node, node_work_dir: pathlib.Path, base_url: str
) -> tuple[str, list[FileSchema]] | None:
    site_config: core_models.SiteConfiguration = await core_models.SiteConfiguration.objects.select_related(
        "main_goingto"
    ).aget()
    if not node_obj.tmp_xray:
        return None
    elif node_obj.collect_metrics and site_config.main_goingto is None:
        logger.critical("no program found for goingto_conf")
        return None
    files = []
    goingto_program = await sync_to_async(site_config.main_goingto.get_program_for_node)(node_obj)
    if goingto_program is None:
        raise ProgramNotFound(program_version=site_config.main_goingto)
    elif isinstance(goingto_program, models.ProgramBinary):
        dest_path = node_work_dir.joinpath("bin", f"goingto_{goingto_program.id}_{goingto_program.hash[:6]}")
        goingto_program_file = FileSchema(
            dest_path=dest_path,
            url=base_url + reverse("node_manager:node_program_binary_content_by_hash", args=[goingto_program.hash]),
            permission=all_permission,
            hash=goingto_program.hash,
        )
    elif isinstance(goingto_program, models.NodeInnerProgram):
        goingto_program_file = FileSchema(
            dest_path=goingto_program.path,
            permission=all_permission,
        )
    else:
        raise AssertionError
    files.append(goingto_program_file)
    template_context = django.template.Context({})
    cnfg_template = """
[xray]
api_port = 6582
api_host = "127.0.0.1"

[xray.usage]
interval = 15
reset = true
"""
    goingto_conf_content = django.template.Template(cnfg_template).render(
        context=django.template.Context(template_context)
    )
    goingto_conf_hash = sha256(goingto_conf_content.encode("utf-8")).hexdigest()
    goingto_conf_content = FileSchema(
        dest_path=node_work_dir.joinpath("conf", f"goingto_{goingto_conf_hash[:6]}"),
        content=goingto_conf_content,
        hash=goingto_conf_hash,
        permission=all_permission,
    )
    files.append(goingto_conf_content)
    supervisor_config = f"""
# config={timezone.now()}
[program:goingto_conf]
command={goingto_program_file.dest_path} --config {goingto_conf_content.dest_path}
autostart=true
autorestart=true
priority=10
"""
    return supervisor_config, files
