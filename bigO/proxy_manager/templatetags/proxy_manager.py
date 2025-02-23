from django import template

from .. import models

register = template.Library()


@register.simple_tag(takes_context=True)
def nginx_include_xtls_paths(context):
    res_parts = []
    for inbound in models.Inbound.objects.all():
        res_parts.append(inbound.nginx_path_config)
    return "\n".join(res_parts)
