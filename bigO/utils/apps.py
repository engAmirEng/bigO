from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TeleportConfig(AppConfig):
    name = "bigO.utils"
    verbose_name = _("Utils")

    def ready(self):
        from django.template import base

        base.render_value_in_context = new_render_value_in_context


def new_render_value_in_context(value, context):
    """
    monkey patch the original django's render_value_in_context to add:
    1-digits_locale
    """
    # 1-digits_locale
    import django.utils.formats
    from django.utils.formats import localize
    from django.utils.html import conditional_escape
    from django.utils.timezone import template_localtime

    if isinstance(value, str):
        if getattr(context, "active_digits_locale"):
            locale_digits_fn = django.utils.formats.get_format("LOCALE_DIGITS")
            if callable(locale_digits_fn):
                value = locale_digits_fn(text=value)
    # end 1

    value = template_localtime(value, use_tz=context.use_tz)
    value = localize(value, use_l10n=context.use_l10n)
    if context.autoescape:
        if not issubclass(type(value), str):
            value = str(value)
        return conditional_escape(value)
    else:
        return str(value)
