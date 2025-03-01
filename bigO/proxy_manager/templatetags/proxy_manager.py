import django.template
from django import template
from django.utils.safestring import mark_safe

from .. import models

register = template.Library()


@register.simple_tag(takes_context=True,)
def nginx_include_xtls_paths(context):
    res_parts = []
    for inbound in models.Inbound.objects.filter(is_active=True):
        res_parts.append(inbound.nginx_path_config)
    return mark_safe("\n".join(res_parts))

@register.simple_tag(takes_context=True,)
def include_xtls_inbounds(context):
    res_parts = []
    for inbound in models.Inbound.objects.filter(is_active=True):
        res_parts.append(inbound.inbound_template)
    temp = "{% load node_manager %}" + (",\n".join(res_parts))
    return django.template.Template(temp).render(context=context)
