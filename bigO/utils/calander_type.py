import functools

from asgiref.local import Local

from django.conf import settings
from django.db import models

_active = Local()


class CalendarType(models.TextChoices):
    GREGORIAN = "gregorian", "gregorian"
    JALALI = "jalali", "jalali"


@functools.lru_cache
def get_default_calendar():
    return CalendarType(settings.CALENDAR_TYPE)


def get_current_calendar():
    return getattr(_active, "value", get_default_calendar())


def activate(cal_type: str):
    if cal_type in CalendarType:
        cal_type = CalendarType(cal_type)
        _active.value = cal_type
    else:
        raise ValueError("Invalid calander: %r" % cal_type)


def deactivate():
    if hasattr(_active, "value"):
        del _active.value
