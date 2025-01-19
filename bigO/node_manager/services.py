import ipaddress
import json
import logging
import random
from datetime import timedelta

import django.template
from bigO.core import models as core_models
from django.db import transaction
from django.db.models import Subquery
from django.utils import timezone
from rest_framework.request import Request

from . import models

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
    obj.request_payload = json.dumps(request.data)
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

    with transaction.atomic():
        privatekey_obj.save()
        certificate_obj.save()
    return certificate_obj


def get_global_nginx_conf(node: models.Node) -> tuple[str, str, dict] | None:
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
user root;
include /etc/nginx/modules-enabled/*.conf;
worker_processes  auto;

events {
    worker_connections  1024;
}
http {
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
}
    """
    result = django.template.Template(cnfg).render(context=django.template.Context(context))
    run_opt = django.template.Template('-c *#path:main#* -g "daemon off;"').render(context=context)
    return run_opt, result, context.get("deps", {"globals": []})
