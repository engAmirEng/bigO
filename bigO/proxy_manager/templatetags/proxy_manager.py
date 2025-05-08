from django import template
from django.utils.safestring import mark_safe

from .. import models

register = template.Library()


@register.simple_tag(
    takes_context=True,
)
def nginx_include_xtls_paths(context):
    res_parts = []
    for inbound in models.InboundType.objects.filter(is_active=True):
        res_parts.append(inbound.nginx_path_config)
    return mark_safe("\n".join(res_parts))


@register.simple_tag(
    takes_context=False,
)
def outboundgroup(outboundgroup_name):
    models.OutboundGroup.objects.get(name=outboundgroup_name)
    return mark_safe(f'"{outboundgroup_name}"')
