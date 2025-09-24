from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(
    takes_context=True,
)
def outboundgroup(context, outboundgroup_name):
    connection_rule = context["connection_rule"]
    balancer_tag = f"{connection_rule.id}_{outboundgroup_name}"
    context["xray_balancers"][balancer_tag]
    return mark_safe(f'"{balancer_tag}"')
