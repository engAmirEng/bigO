from django.template.loader import render_to_string


def thtml_render_to_string(template_name, context=None, request=None, using=None):
    rendered = render_to_string(template_name, context=context, request=request, using=using)
    lines = rendered.replace("\n", "").split("<br>")
    result_lines = []
    for line in lines:
        line: str
        result_lines.append(line.lstrip().rstrip().replace("&nbsp;", " "))
    return "\n".join(result_lines)
