from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import ClassVar, Optional, Type, Union

import django_jsonform.models.fields

import django.template
from bigO.utils.models import TimeStampedModel
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy

from ...users.models import User
from ..providers import AVAILABLE_PROVIDERS, BaseNotificationProvider, NotificationInput


class NotificationAccount(TimeStampedModel, models.Model):
    name = models.SlugField(max_length=255, unique=True)
    provider = models.CharField(max_length=255)
    type = models.CharField(max_length=15, choices=BaseNotificationProvider.Type.choices, blank=True)
    extras = models.JSONField(null=True, blank=True)
    cost_ratio = models.DecimalField(max_digits=6, decimal_places=2, default=1)

    class Meta:
        verbose_name = "Notification Account"

    def __str__(self):
        return f"{self.id}-{self.name}"

    def get_provider_class(self) -> type[BaseNotificationProvider]:
        return [i for i in AVAILABLE_PROVIDERS if i.KEY == self.provider][0]

    def get_provider_instance(self) -> BaseNotificationProvider:
        return self.get_provider_class().initialize_from_account(self)

    def set_pricing(self, base_cost: Decimal):
        assert self.notification_account is not None
        self.base_cost = base_cost
        self.final_cost = base_cost * self.notification_account.cost_ratio

    def save(self, *args, **kwargs):
        if self.provider is not None and self.type != self.get_provider_class().TYPE:
            logger.critical(f"{str(self)} was inconsistent in provider")
        self.type = self.get_provider_class().TYPE
        return super().save(*args, **kwargs)


class Notification(TimeStampedModel, models.Model):
    notification_account = models.ForeignKey(
        NotificationAccount, on_delete=models.PROTECT, related_name="notifications"
    )
    to_user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        related_name="notifications",
        null=True,
        blank=False,
    )
    base_cost = models.DecimalField(max_digits=10, decimal_places=2)
    final_cost = models.DecimalField(max_digits=10, decimal_places=2)

    def set_pricing(self, base_cost: Decimal):
        assert self.notification_account is not None
        self.base_cost = base_cost
        self.final_cost = base_cost * self.notification_account.cost_ratio


class MessageContext(TimeStampedModel, models.Model):
    key = models.CharField(max_length=255)
    value = models.TextField()

    class Meta:
        verbose_name = gettext_lazy("Message Context")

    def __str__(self):
        return f"{self.id}-{self.key}"

    def clean_key(self):
        try:
            ConstMessageContext.get_by_key(self.key)
        except IndexError:
            raise ValidationError(_("{key} does not exist in the registered ConstMessageContext").format(key=self.key))

    def clean_value(self):
        variable_nodes = Template(self.value).nodelist.get_nodes_by_type(VariableNode)
        const_message_context = ConstMessageContext.get_by_key(self.key)
        for variable_node in variable_nodes:
            var = variable_node.filter_expression.var.lookups[0]
            if var not in const_message_context.context:
                raise ValidationError(_("{var_name} is not available").format(var_name=var))

    def clean(self):
        self.clean_key()
        self.clean_value()


class ForeignTemplate(TimeStampedModel, models.Model):
    FOREIGN_MAPPING_SCHEMA = {
        "type": "object",
        "properties": {
            "mapping": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "foreign_name": {"type": "string"},
                        "accessor": {"type": "string"},
                    },
                    "required": ["context_name", "foreign_name", "accessor"],
                },
            },
        },
    }

    notification_account = models.ForeignKey(
        NotificationAccount,
        on_delete=models.PROTECT,
        related_name="foreigntemplate",
    )
    const_message_key = models.CharField(max_length=255)
    foreign_template_name = models.CharField(max_length=255)
    foreign_mapping = django_jsonform.models.fields.JSONField(schema=FOREIGN_MAPPING_SCHEMA)

    class Meta:
        verbose_name = "Foreign Template"

    def get_foreign_mapping(self, context: dict):
        res = {}
        mapping: list = self.foreign_mapping.get("mapping", [])
        for m in mapping:
            res[m["foreign_name"]] = django.template.Template(m["accessor"]).render(
                context=django.template.Context(context)
            )
        return res


class NotifiedMessageContext(TimeStampedModel, models.Model):
    message_context = models.ForeignKey(
        MessageContext,
        on_delete=models.SET_NULL,
        related_name="notifiedmessagecontexts",
        null=True,
        blank=False,
    )
    foreign_template = models.ForeignKey(
        ForeignTemplate,
        on_delete=models.SET_NULL,
        related_name="notifiedmessagecontexts",
        null=True,
        blank=True,
    )
    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="notifiedmessagecontexts",
    )
    as_var = models.CharField(max_length=63, choices=NotificationInput.choices)
    actual_message = models.TextField()

    class Meta:
        verbose_name = "Notified Message Context"

    @staticmethod
    def get_send_kwarg(
        notification_message_contexts: List[NotifiedMessageContextModel],
        available_vars: Set[str],
    ) -> Dict[str, str | OuterTemplateInput]:
        res = {}
        for i in notification_message_contexts:
            if i.as_var not in available_vars:
                continue
            if i.foreign_template:
                res[i.as_var] = {
                    "template_name": i.foreign_template.foreign_template_name,
                    "template_kwargs": json.loads(i.actual_message),
                }
            elif i.actual_message:
                res[i.as_var] = i.actual_message
            else:
                raise AssertionError
        return res


def get_contex_message_text(
    key: ConstMessageContext | str,
    context: Mapping,
    assert_context: bool = False,
    return_message_context_obj: bool = False,
) -> str | tuple[str, MessageContextModel | None]:
    if assert_context:
        if not isinstance(key, ConstMessageContext):
            key = ConstMessageContext.get_by_key(key=key)
        context = {**context, "shop": shop}
        assert key.context.issubset(context.keys())

    key = key if type(key) == str else key.key
    message_context = MessageContext.objects.filter(key=key).last()
    if message_context is None:
        if return_message_context_obj:
            return "", None
        return ""
    text = django.template.Template(message_context.value).render(context=django.template.Context(dict_=context))
    if return_message_context_obj:
        return text, message_context
    return text


get_contex_message_text_lazy = lazy(get_contex_message_text, str)


class ConstMessageContext:
    """
    This is something like a singleton
    """

    instances: ClassVar[set[ConstMessageContext]] = set()

    def __init__(self, key: str, context: set[str]):
        self.key = key
        self.context = context

        self.instances.add(self)

    def __hash__(self):
        return hash(self.key)

    def __eq__(self, other):
        return self.key == other.key

    @classmethod
    def get_by_key(cls, key: str):
        """
        :raises IndexError in not exist
        """
        return [i for i in cls.instances if i.key == key][0]

    @classmethod
    def choices(cls):
        return [(i.key, i.key) for i in cls.instances]


customer = ConstMessageContext(key="customer", context=set())
driver = ConstMessageContext(key="driver", context=set())
operator = ConstMessageContext(key="operator", context=set())
dont_forget_reservation_body = ConstMessageContext(
    key="dont_forget_reservation_body", context={"reservation_datetime_str", "shop"}
)
dont_forget_reservation_title = ConstMessageContext(key="dont_forget_reservation_title", context=set())
your_reservation_registered = ConstMessageContext(
    key="your_reservation_registered", context={"shop_name", "reservation_datetime_str"}
)
survey_text = ConstMessageContext(
    key="survey_text",
    context={"mobile", "first_name", "last_name", "shop_name", "full_name", "url"},
)
how_was_your_order = ConstMessageContext(
    key="how_was_your_order",
    context={"first_name", "last_name", "shop_name", "full_name", "url"},
)
your_order_registered = ConstMessageContext(
    key="your_order_registered",
    context={"customer_first_name", "follow_up_link", "shop_name"},
)
did_not_answered_to_delivery = ConstMessageContext(
    key="did_not_answered_to_delivery",
    context={"customer_first_name", "driver_mobile", "shop_name"},
)
this_is_your_entrance_verification_code = ConstMessageContext(
    key="this_is_your_entrance_verification_code",
    context={"code", "shop", "domain"},
)
you_have_been_successfully_entered_panel = ConstMessageContext(
    key="you_have_been_successfully_entered_panel",
    context={"shop", "user", "datetime_str"},
)
axes_lockout_message = ConstMessageContext(
    key="axes_lockout_message",
    context={"failure_limit", "cooloff_datetime"},
)


send_order_in_progress_status_sms_message = ConstMessageContext(
    key="send_order_in_progress_status_sms",
    context={"shop_name"},
)
send_order_ready_status_sms_message = ConstMessageContext(
    key="send_order_ready_status_sms",
    context={"shop_name"},
)
send_order_completed_status_sms_message = ConstMessageContext(
    key="send_order_completed_status_sms",
    context={"shop_name"},
)
send_happy_birthday_sms_message = ConstMessageContext(
    key="send_happy_birthday_sms",
    context={"customer_full_name", "shop_name"},
)
