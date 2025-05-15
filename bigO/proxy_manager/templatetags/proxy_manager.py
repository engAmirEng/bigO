from django import template
from django.utils.safestring import mark_safe

from .. import models

register = template.Library()


@register.simple_tag(
    takes_context=True,
)
def nginx_include_xtls_paths(context):
    """
    deprecated
    """
    res_parts = []
    for inbound in models.InboundType.objects.filter(is_active=True):
        res_parts.append(inbound.nginx_path_config)
    return mark_safe("\n".join(res_parts))


@register.simple_tag(
    takes_context=True,
)
def outboundgroup(context, outboundgroup_name):
    connection_rule = context["connection_rule"]
    balancer_tag = f"{connection_rule.id}_{outboundgroup_name}"
    context["xray_balancers"][balancer_tag]
    return mark_safe(f'"{balancer_tag}"')
