from hashlib import sha256

import django.template.context
from bigO.core import models as core_models
from django import template
from django.utils import timezone

from .. import models, services, typing

register = template.Library()


@register.simple_tag
def easytier_ips(source_node: models.Node, dest_node_id):
    res = services.get_easytier_to_node_ips(source_node=source_node, dest_node_id=dest_node_id)
    return [str(i) for i in res]


def certificate_getter(certs, pem: bool, context: services.NodeTemplateContext | django.template.Context):
    res = []
    if isinstance(context, services.NodeTemplateContext):
        for cert in certs:
            if pem:
                pem_content = cert.get_full_pem_content()
                pem_hash = sha256(pem_content.encode()).hexdigest()
                cert_content_file = typing.FileSchema(
                    dest_path=context.node_work_dir.joinpath("conf", f"{cert.slug}_{pem_hash[:6]}.pem"),
                    content=pem_content,
                    hash=pem_hash,
                    permission=services.all_permission,
                )
                services.add_configdependentcontent_to_context(
                    context=context, configdependentcontent=cert_content_file
                )
                res.append(cert_content_file.dest_path)
            else:
                cert_content = cert.get_fullchain_content()
                cert_hash = sha256(cert_content.encode()).hexdigest()
                cert_content_file = typing.FileSchema(
                    dest_path=context.node_work_dir.joinpath("conf", f"{cert.slug}_{cert_hash[:6]}.cert"),
                    content=cert_content,
                    hash=cert_hash,
                    permission=services.all_permission,
                )
                key_hash = sha256(cert.private_key.content.encode()).hexdigest()
                key_content_file = typing.FileSchema(
                    dest_path=context.node_work_dir.joinpath("conf", f"{cert.private_key.slug}_{key_hash[:6]}.key"),
                    content=cert.private_key.content,
                    hash=key_hash,
                    permission=services.all_permission,
                )
                services.add_configdependentcontent_to_context(
                    context=context, configdependentcontent=cert_content_file
                )
                services.add_configdependentcontent_to_context(
                    context=context, configdependentcontent=key_content_file
                )
                res.append({"cert": cert_content_file.dest_path, "key": key_content_file.dest_path})
        return res

    context["deps"] = context.get("deps", {"globals": []})
    for i in certs:
        cert_key = f"{i.slug}"
        key_key = f"{i.slug}_key"
        context["deps"]["globals"].append(cert_key)
        context["deps"]["globals"].append(key_key)
        res.append({"cert": f"*#path:{cert_key}#*", "key": f"*#path:{key_key}#*"})
    return res


@register.simple_tag(takes_context=True)
def default_cert2(context: services.NodeTemplateContext | django.template.Context, node: models.Node, pem=False):
    default_cert = node.get_default_cert()
    return certificate_getter([default_cert], pem=pem, context=context)[0]


@register.simple_tag(takes_context=True)
def allowed_valid_certs(context: services.NodeTemplateContext | django.template.Context, node: models.Node, pem=False):
    certificate_qs = core_models.Certificate.objects.filter(
        certificate_domaincertificates__isnull=False, valid_to__gt=timezone.now()
    )
    return certificate_getter(list(certificate_qs), pem=pem, context=context)


@register.simple_tag(takes_context=True)
def default_basic_http_file(context: services.NodeTemplateContext | django.template.Context, node: models.Node):
    if isinstance(context, services.NodeTemplateContext):
        site_config: core_models.SiteConfiguration = core_models.SiteConfiguration.objects.get()
        htpasswd_content_hash = sha256(site_config.htpasswd_content.encode()).hexdigest()
        passed_content_file = typing.FileSchema(
            dest_path=context.node_work_dir.joinpath("conf", f"passwd_{htpasswd_content_hash[:6]}"),
            content=site_config.htpasswd_content,
            hash=htpasswd_content_hash,
            permission=services.all_permission,
        )
        services.add_configdependentcontent_to_context(context=context, configdependentcontent=passed_content_file)
        return passed_content_file.dest_path

    context["deps"] = context.get("deps", {"globals": []})
    context["deps"]["globals"].append("default_basic_http_file")
    return "*#path:default_basic_http_file#*"
