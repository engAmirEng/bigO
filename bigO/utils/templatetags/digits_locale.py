import django.utils.formats
from django import template

register = template.Library()


class DigitsLocaleNode(template.Node):
    def __init__(self, nodelist, active=True):
        self.nodelist = nodelist
        self.active = active

    def render(self, context):
        # render with a state stack
        stack = context.render_context.setdefault("digits_locale_stack", [self.active])
        return self._render_nodelist(self.nodelist, context, stack)

    def _render_nodelist(self, nodelist, context, stack):
        result = ""
        for node in nodelist:
            # nested control node
            if isinstance(node, DigitsLocaleControlNode):
                stack.append(node.active)
                result += self._render_nodelist(node.nodelist, context, stack)
                stack.pop()
            else:
                text = node.render(context)
                if stack[-1]:
                    locale_digits_fn = django.utils.formats.get_format("LOCALE_DIGITS")
                    if callable(locale_digits_fn):
                        text = locale_digits_fn(text=text)
                    else:
                        text = text
                result += text
        return result


class DigitsLocaleControlNode(template.Node):
    def __init__(self, active, nodelist):
        self.active = active
        self.nodelist = nodelist


@register.tag("digits_locale")
def digits_locale(parser, token):
    bits = token.split_contents()
    # Default for outermost tag
    active = True
    if len(bits) == 2:
        if bits[1].lower() == "on":
            active = True
        elif bits[1].lower() == "off":
            active = False
        else:
            raise template.TemplateSyntaxError("digits_locale tag only supports 'on' or 'off'")

    nodelist = []
    while True:
        node = parser.parse(("digits_locale", "enddigits_locale"))
        # parser.parse stops at first end token
        nodelist.extend(node)
        next_token = parser.next_token()
        parts = next_token.contents.split()
        if parts[0] == "enddigits_locale":
            break
        elif parts[0] == "digits_locale":
            if len(parts) != 2 or parts[1] not in ("on", "off"):
                raise template.TemplateSyntaxError("digits_locale tag only supports 'on' or 'off'")
            child_nodelist = parser.parse(("enddigits_locale",))
            parser.delete_first_token()
            nodelist.append(DigitsLocaleControlNode(parts[1] == "on", child_nodelist))
    return DigitsLocaleNode(nodelist, active)
