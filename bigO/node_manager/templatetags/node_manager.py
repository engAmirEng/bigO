from bigO.core import models as core_models
from django import template
from django.utils import timezone

from .. import models, services

register = template.Library()


@register.simple_tag
def easytier_ips(source_node: models.Node, dest_node_id):
    res = services.get_easytier_to_node_ips(source_node=source_node, dest_node_id=dest_node_id)
    return [str(i) for i in res]


@register.simple_tag(takes_context=True)
def default_cert(context, node: models.Node):
    context["deps"] = context.get("deps", {"globals": []})
    context["deps"]["globals"].append("default_cert")
    return "*#path:default_cert#*"


@register.simple_tag(takes_context=True)
def default_cert_key(context, node: models.Node):
    context["deps"] = context.get("deps", {"globals": []})
    context["deps"]["globals"].append("default_cert_key")
    return "*#path:default_cert_key#*"


@register.simple_tag(takes_context=True)
def allowed_valid_certs(context, node: models.Node):
    certificate_qs = core_models.Certificate.objects.filter(
        certificate_domaincertificates__isnull=False, valid_to__gt=timezone.now()
    )
    res = []
    context["deps"] = context.get("deps", {"globals": []})
    for i in certificate_qs:
        cert_key = f"{i.slug}"
        key_key = f"{i.slug}_key"
        context["deps"]["globals"].append(cert_key)
        context["deps"]["globals"].append(key_key)
        res.append({"cert": f"*#path:{cert_key}#*", "key": f"*#path:{key_key}#*"})
    return res


@register.simple_tag(takes_context=True)
def default_basic_http_file(context, node: models.Node):
    context["deps"] = context.get("deps", {"globals": []})
    context["deps"]["globals"].append("default_basic_http_file")
    return "*#path:default_basic_http_file#*"
