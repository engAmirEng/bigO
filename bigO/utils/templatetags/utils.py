import base64
import random
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

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


class UrlencodeNode(template.Node):
    def __init__(self, nodelist):
        self.nodelist = nodelist

    def render(self, context):
        content = self.nodelist.render(context)
        # Split URL
        parts = urlsplit(content)

        # Encode query values properly
        query = urlencode(parse_qsl(parts.query, keep_blank_values=True), safe="")

        # Encode fragment
        fragment = quote(parts.fragment, safe="")

        # Rebuild URL
        string2 = urlunsplit((parts.scheme, parts.netloc, parts.path, query, fragment))
        return string2


@register.tag(name="urlencode")
def do_urlencode(parser, token):
    """
    Usage:
        {% b64 %}
        content
        {% endb64 %}
    """
    nodelist = parser.parse(("endburlencode",))
    parser.delete_first_token()
    return UrlencodeNode(nodelist)


@register.simple_tag
def randchoice(*choices):
    """
    Usage:
        {% randchoice "A:2" "B:3" "C:1" %}

    Returns one value based on weighted probability.
    """
    values = []
    weights = []

    for choice in choices:
        try:
            value, weight = choice.rsplit(":", 1)
            weight = int(weight)
        except ValueError:
            continue  # skip invalid input

        if weight > 0:
            values.append(value)
            weights.append(weight)

    if not values:
        return ""

    return random.choices(values, weights=weights, k=1)[0]
