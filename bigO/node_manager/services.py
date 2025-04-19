import datetime
import ipaddress
import json
import logging
import pathlib
import random
import re
import tomllib
import zoneinfo
from datetime import timedelta

from pyasn1_modules.rfc5990 import sha256

import django.template
from bigO.core import models as core_models
from bigO.proxy_manager import services as services_models
from config import settings
from django.db import transaction
from django.db.models import Subquery
from django.utils import timezone
from rest_framework.request import Request

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
    smallo1_logs: typing.SupervisorProcessTailLogSerializerSchema | None,
):
    streams: list[typing.LokiStram] = []
    configs_states = configs_states or []
    base_labels = {"service_name": "bigo", "node_id": node_obj.id, "node_name": node_obj.name}
    for i in configs_states:
        service_name = i.supervisorprocessinfo.name
        send_stdout = False
        send_stderr = False
        if service_name.startswith("custom_"):
            ___, cc_id, ncci = service_name.split("_")
            try:
                nodecustomconfig_obj = models.NodeCustomConfig.objects.get(node=node_obj, custom_config_id=cc_id)
            except models.NodeCustomConfig.DoesNotExist:
                logger.info(f"node service name {service_name} not found for node_process_stats")
                continue
            send_stdout = nodecustomconfig_obj.stdout_action_type == core_models.LogActionType.TO_LOKI
            send_stderr = nodecustomconfig_obj.stderr_action_type == core_models.LogActionType.TO_LOKI
        if service_name.startswith("eati_"):
            ___, etn_id = service_name.split("_")
            try:
                easytiernode_obj = models.EasyTierNode.objects.get(id=etn_id)
                send_stdout = easytiernode_obj.stdout_action_type == core_models.LogActionType.TO_LOKI
                send_stderr = easytiernode_obj.stderr_action_type == core_models.LogActionType.TO_LOKI
            except models.EasyTierNode.DoesNotExist:
                logger.info(f"node service name {service_name} not found for node_process_stats")
                continue
        if service_name == "global_nginx_conf":
            continue
        if (
            node_obj.collect_metrics
            and service_name == "telegraf_conf"
            and i.stdout.bytes
            and getattr(settings, "INFLUX_URL", False)
        ):
            tasks.telegraf_to_influx_send.delay(telegraf_json_lines=i.stdout.bytes, base_labels=base_labels)
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


def create_node_sync_stat(request: Request, node: models.Node) -> models.NodeLatestSyncStat:
    try:
        obj = models.NodeLatestSyncStat.objects.get(node=node)
    except models.NodeLatestSyncStat.DoesNotExist:
        obj = models.NodeLatestSyncStat(node=node)
    obj.request_headers = json.dumps(dict(request.headers))
    obj.initiated_at = timezone.now()
    obj.agent_spec = request._request.headers.get("user-agent", "")[:200]
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


def get_global_haproxy_conf(node: models.Node) -> tuple[str, str, dict] | None:
    context = django.template.Context({})
    res = django.template.Template(
        """global
        log /dev/log local0

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
        bind :443,:::443 v4v6
        bind :443,:::443 v4v6 tfo
        # option tcplog
        # option dontlognull
        tcp-request inspect-delay 5s
        tcp-request content accept if { req.ssl_hello_type 1 }
        use_backend xray_force

    backend xray_force
        # server xray unix@/dev/shm/hiddify-xtls-main.sock
        server xray unix@/var/run/o_xtls_main.sock send-proxy-v2
    """
    ).render(context=context)

    run_opt = django.template.Template("-f *#path:main#* -d").render(context=context)
    return run_opt, res, context.get("deps", {"globals": []})


def get_global_nginx_conf(node: models.Node) -> tuple[str, str, dict] | None:
    usage = False
    deps = {}
    http_part = ""
    stream_part = ""

    supervisor_nginx_conf = get_supervisor_nginx_conf(node=node)
    if supervisor_nginx_conf:
        http_part += supervisor_nginx_conf[0]
        deps = supervisor_nginx_conf[1]
        usage = True
    proxy_manager_nginx_conf = services_models.get_proxy_manager_nginx_conf(node_obj=node)
    if proxy_manager_nginx_conf[0] or proxy_manager_nginx_conf[1]:
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


def get_supervisor_nginx_conf(node: models.Node) -> tuple[str, dict] | None:
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
    def __init__(self, *args, program_version, **kwargs):
        super().__init__(*args, **kwargs)
        self.program_version = program_version


def get_configdependentcontents_from_context(context: django.template.Context) -> list[FileSchema]:
    return context.get("deps", {}).get("dependents", [])


def add_configdependentcontent_to_context(
    context: django.template.Context, configdependentcontent: typing.FileSchema
):
    deps = context.get("deps", {"dependents": []})
    deps["dependents"].append(configdependentcontent)


def get_deps(template: str) -> list[tuple[str, str]]:
    matches = re.findall(r"\*#(\w+):(\w+)#\*", template)
    return [tuple(i.split(":")) for i in matches]


def render_deps(template: str, deps: set[str], proccessed_dependantfiles_map: dict[str, FileSchema]):
    for dep in deps:
        template = template.replace(f"*#path:{dep}#*", proccessed_dependantfiles_map[dep].dest_path)
    return template


def get_customconfig_proccessname(customconfig: models.CustomConfig):
    return f"custom_{custom_config.id}"


all_permission = 744


async def get_custom(
    node: models.Node, customconfig: models.CustomConfig, node_work_dir: pathlib.Path, host_name: str
) -> tuple[str, list[FileSchema]]:
    files = []
    unproccessed_dependantfiles_map = {}
    proccessed_dependantfiles_map = {}
    template_context = {
        "node_obj": node,
    }
    async for dependantfile in customconfig.dependantfiles.all():
        if dependantfile.template:
            template = django.template.Template("{% load node_manager %}" + dependantfile.template)
            rendered_template = template.render(context=django.template.Context(template_context))
            unproccessed_dependantfiles_map[dependantfile.name] = rendered_template
        elif dependantfile.file:
            file = dependantfile.file.get_program_for_node(node)
            if file is None:
                raise ProgramNotFound()
            elif isinstance(file, models.ProgramBinary):
                dest_path = node_work_dir.joinpath("bin", f"{file.program_version_id}_{file.hash[:6]}")
                url = get_absolute_url(reverse("node_manager:node_program_binary_content_by_hash", args=[content_hash]))
                proccessed_dependantfiles_map[dependantfile.name] = FileSchema(
                    dest_path=dest_path, url=url, pepermission=all_permission, hash=file.hash
                )
            elif isinstance(file, models.NodeInnerProgram):
                dest_path = file.path
                proccessed_dependantfiles_map[dependantfile.name] = FileSchema(
                    dest_path=dest_path, pepermission=all_permission
                )
            else:
                raise AssertionError
        else:
            raise AssertionError

    dependantfiles_deps = defaultdict(set)
    for key, template in unproccessed_dependantfiles_map.items():
        deps = get_deps(template)
        for dep in deps:
            dependantfiles_deps[key].add(dep[1])

    while unproccessed_dependantfiles_map:
        next_to_resolve_key = [
            key
            for key, deps in unproccessed_dependantfiles_map.items()
            if not (dependantfiles_deps[key] - proccessed_dependantfiles_map.keys())
        ]
        if not next_to_resolve_key:
            raise AssertionError
        next_to_resolve_key = next_to_resolve_key[0]
        template = unproccessed_dependantfiles_map[next_to_resolve_key]
        deps = dependantfiles_deps[next_to_resolve_key]
        content = render_deps(template, deps, proccessed_dependantfiles_map)
        content_hash = sha256(content.encode("utf-8")).hexdigest()
        proccessed_dependantfiles_map[next_to_resolve_key] = FileSchema(
            dest_path=node_work_dir.joinpath("conf", f"{customconfig.id}_{content_hash[:6]}_{next_to_resolve_key}"), content=content, hash=content_hash, pepermission=all_permission
        )
        unproccessed_dependantfiles_map.pop(next_to_resolve_key)

    run_opts_template = django.template.Template("{% load node_manager %}" + custom_config.run_opts_template)
    run_opts_rendered_template = run_opts_template.render(context=django.template.Context(template_context))
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


def get_easytier(
    easytiernode_obj: models.EasyTierNode, node_work_dir: pathlib.Path, host_name: str
) -> tuple[str, list[FileSchema]]:
    toml_config_content = easytiernode_obj.get_toml_config_content()
    try:
        tomllib.loads(toml_config_content)
    except tomllib.TOMLDecodeError as e:
        raise IncorrectTemplateFormat(e)
    files = []
    toml_config_content_hash = sha256(toml_config_content.encode("utf-8")).hexdigest()
    files.append(
        FileSchema(
            dest_path=node_work_dir.joinpath("conf", f"eati_{easytiernode_obj.id}_{toml_config_content_hash[:6]}.toml"),
            content=toml_config_content,
            hash=toml_config_content_hash,
            permission=all_permission,
        )
    )
    program_version = self.preferred_program_version or self.network.program_version
    program = program_version.get_program_for_node(easytiernode_obj.node)
    if program is None:
        raise ProgramNotFound(program_version=program_version)
    elif isinstance(program, models.ProgramBinary):
        easytier_program_file = FileSchema(
            dest_path=node_work_dir.joinpath("bin", f"{program.program_version_id}_{program.hash[:6]}"),
            url=get_absolute_url(reverse("node_manager:node_program_binary_content_by_hash", args=[content.hash])),
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
    conf_file = FileSchema(
        content=toml_config_content,
        hash=sha256(toml_config_content.encode("utf-8")).hexdigest(),
        permission=all_permission,
    )
    files.append(conf_file)
    run_opts = easytiernode_obj.get_run_opts()
    supervisor_config = f"""
# config={timezone.now()}
[program:eati_{easytiernode_obj.id}]
command={easytier_program_file.dest_path} {run_opts}
autostart=true
autorestart=true
priority=10
"""
    return supervisor_config, files


async def get_telegraf(node_obj: models.Node, node_work_dir: pathlib.Path, host_name: str) -> tuple[str, list[
    FileSchema]] | None:
    site_config: core_models.SiteConfiguration = await core_models.SiteConfiguration.objects.aget()
    telegraf_conf = get_telegraf_conf(node=node_obj)
    if telegraf_conf is None:
        return None
    elif telegraf_conf and site_config.main_telegraf is None:
        logger.critical("no program found for telegraf_conf")
        return None
    telegraf_program = site_config.main_telegraf.get_program_for_node(node_obj)
    if telegraf_program is None:
        raise ProgramNotFound(program_version=site_config.main_telegraf)
    elif isinstance(telegraf_program, models.ProgramBinary):
        dest_path = node_work_dir.joinpath("bin", f"telegraf_{telegraf_program.id}_{telegraf_program.hash[:6]}")
        telegraf_program_file = FileSchema(
            dest_path=dest_path,
            url=get_absolute_url(
                reverse("node_manager:node_program_binary_content_by_hash", args=[telegraf_program.hash])
            ),
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
    files = []
    files.append(telegraf_program_file)
    telegraf_conf_hash = sha256(telegraf_conf.encode("utf-8")).hexdigest()
    conf_file = FileSchema(
        dest_path=node_work_dir.joinpath("conf", f"telegraf_{telegraf_conf_hash[:6]}"), content=telegraf_conf, hash=telegraf_conf_hash, permission=all_permission
    )
    files.append(conf_file)
    supervisor_config = f"""
# config={timezone.now()}
[program:telegraf_conf]
command={telegraf_program_file.dest_path} {telegraf_conf}
autostart=true
autorestart=true
priority=10
"""
    return supervisor_config, files
