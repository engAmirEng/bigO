import base64

from django import template

register = template.Library()


class Base64Node(template.Node):
    def __init__(self, nodelist):
        self.nodelist = nodelist

    def render(self, context):
        content = self.nodelist.render(context)
        encoded = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        return encoded


@register.tag(name="b64")
def do_base64(parser, token):
    """
    Usage:
        {% b64 %}
        content
        {% endb64 %}
    """
    nodelist = parser.parse(("endb64",))
    parser.delete_first_token()
    return Base64Node(nodelist)
