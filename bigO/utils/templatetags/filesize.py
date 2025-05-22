import humanize.filesize

from django.template import Library

register = Library()


@register.filter(is_safe=True)
def filesize(bytes_):
    return humanize.naturalsize(bytes_)
