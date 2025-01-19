from django import template

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
def default_basic_http_file(context, node: models.Node):
    context["deps"] = context.get("deps", {"globals": []})
    context["deps"]["globals"].append("default_basic_http_file")
    return "*#path:default_basic_http_file#*"
