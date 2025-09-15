import humanize

from django.template import Library

register = Library()


@register.filter(is_safe=True)
def filesize(bytes_):
    return humanize.naturalsize(bytes_)


@register.filter(is_safe=True)
def convert_SI(bytes_):
    """
    since some apps/services do not know the diff between (KiB, MiB, GiB) and (KB, MB, GB)
    """
    if bytes_ < 1000:
        return bytes_

    size = float(bytes_)
    res = bytes_
    idx = 1
    while size >= 1000 and idx < 10:
        size /= 1000
        res = res * 1024 / 1000

    return int(res)
