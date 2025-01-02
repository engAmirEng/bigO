from django import template

from .. import models, services

register = template.Library()


@register.simple_tag
def easytier_ips(source_node: models.Node, dest_node_id):
    res = services.get_easytier_to_node_ips(source_node=source_node, dest_node_id=dest_node_id)
    return [str(i) for i in res]


@register.simple_tag
def default_cert(node: models.Node):
    return "*#path:default_cert#*"


@register.simple_tag
def default_cert_key(node: models.Node):
    return "*#path:default_cert_key#*"
