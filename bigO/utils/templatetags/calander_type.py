from datetime import date, datetime

import jdatetime

from django.template import Library

from .. import calander_type

register = Library()


@register.filter(expects_localtime=True, is_safe=False)
def time_format(value, arg=None):
    """Formats a date or time according to the given format."""
    if value in (None, ""):
        return ""
    if arg is None:
        arg = "%c"
    caltype = calander_type.get_current_calendar()

    try:
        if isinstance(value, datetime):
            if caltype == calander_type.CalendarType.GREGORIAN:
                value = value
            elif caltype == calander_type.CalendarType.JALALI:
                value = jdatetime.datetime.fromgregorian(datetime=value)
            else:
                raise NotImplementedError
        elif isinstance(value, date):
            if caltype == calander_type.CalendarType.GREGORIAN:
                value = value
            elif caltype == calander_type.CalendarType.JALALI:
                value = jdatetime.date.fromgregorian(date=value)
            else:
                raise NotImplementedError
        return value.strftime(arg)
    except AttributeError:
        return ""
