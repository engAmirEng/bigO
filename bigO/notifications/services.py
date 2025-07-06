import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Union

from bigO.notifications.models import ConstMessageContext, get_contex_message_text
from bigO.notifications.providers import BaseNotificationProvider, NotificationInput
from bigO.users.models import User
from django.db.models import TextChoices
from django.utils import translation

from . import models

logger = logging.getLogger(__name__)


@dataclass
class NotificationMessagePart:
    const_message_context: ConstMessageContext | str
    context: dict

    def calc(
        self, account: models.NotificationAccount
    ) -> tuple[str, models.MessageContext] | tuple[dict, "models.ForeignTemplate"]:
        foreign_template = models.ForeignTemplate.objects.filter(
            notification_account=account,
            const_message_key=(
                self.const_message_context.key
                if isinstance(self.const_message_context, ConstMessageContext)
                else self.const_message_context
            ),
        ).first()
        if foreign_template:
            foreign_mapping = foreign_template.get_foreign_mapping(self.const_message_context)
            return foreign_mapping, foreign_template
        else:
            msg, obj = get_contex_message_text(
                self.const_message_context,
                self.context,
                assert_context=True,
                return_message_context_obj=True,
            )
            return msg, obj


MessageType = dict[NotificationInput, Union[NotificationMessagePart, str]]
CostType = Decimal


class NotSentReason(TextChoices):
    NOT_REGISTERED_MESSAGE = "not_registered_message"
    NO_NOTIFICATION_ACCOUNT = "no_notification_account"
    NONE_OF_ACCOUNTS_SUCCEEDED = "none_of_accounts_succeeded"


def send_notification(
    to: "User",
    message: "MessageType",
    type_priorities: list[BaseNotificationProvider.Type],
) -> tuple[Literal[True], BaseNotificationProvider.Type] | tuple[Literal[False], NotSentReason]:
    message = {i: v for i, v in message.items() if v}

    notification_accounts = list(models.NotificationAccount.objects.all())
    if not notification_accounts:
        logger.warning(f"No NotificationAccountModel found")
        return False, NotSentReason.NO_NOTIFICATION_ACCOUNT

    for type_priority in type_priorities:
        notification_account = [i for i in notification_accounts if i.type == type_priority]
        notification_account_obj: models.NotificationAccount | None = (
            notification_account[0] if notification_account else None
        )
        if notification_account_obj is None:
            logger.info(f"no candidate for {type_priority}")
            continue

        (
            is_succeed,
            cost,
            notified_message_contexts,
        ) = account_send_notification(notification_account_obj, message=message, to=to)
        if is_succeed:
            log_notification(
                notification_account_obj=notification_account_obj,
                cost=cost,
                to=to,
                notified_message_contexts=notified_message_contexts,
            )
            return True, type_priority
        else:
            continue
    logger.warning(f"no notification_account found for {str(shop)} in {str(type_priorities)}")
    return False, NotSentReason.NONE_OF_ACCOUNTS_SUCCEEDED


def account_send_notification(
    notification_account_obj, message: MessageType, to: User
) -> tuple[Literal[True], CostType, list[models.NotifiedMessageContext]] | tuple[Literal[False], NotSentReason, None]:
    available_vars = notification_account_obj.get_provider_class().get_available_send_vars()
    try:
        notified_message_contexts = get_notified_message_contexts(
            notification_account_obj,
            message=message,
            lang=translation.get_language(),
        )
        notified_message_contexts = [i for i in notified_message_contexts if i.as_var in available_vars]
    except NoMessageException:
        return False, NotSentReason.NOT_REGISTERED_MESSAGE, None

    is_succeed, cost = notification_account_obj.get_provider_instance().send(
        to=to,
        **models.NotifiedMessageContext.get_send_kwarg(notified_message_contexts, available_vars),
    )
    return is_succeed, cost, notified_message_contexts


def get_notified_message_contexts(
    notification_account_obj,
    message: dict[str, NotificationMessagePart | str],
    lang: str,
) -> list[models.NotifiedMessageContext]:
    """
    :raises NoMessageForThisShopException if any of messages is not registered,
    then you should skip sending this notif completely
    """
    notified_message_contexts = []
    for var_key, var_v in message.items():
        if var_v is not None:
            translation.activate(lang)
            if isinstance(var_v, NotificationMessagePart):
                title_msg, title_obj = var_v.calc(account=notification_account_obj)
                if title_obj is None:
                    raise NoMessageException
            else:
                title_msg, title_obj = var_v, None
            notification = models.NotifiedMessageContext(
                as_var=var_key,
            )
            if isinstance(title_obj, models.ForeignTemplate):
                notification.foreign_template = title_obj
                notification.actual_message = json.dumps(title_msg)
            else:
                notification.message_context = title_obj
                notification.actual_message = title_msg
            notified_message_contexts.append(notification)
            translation.deactivate()
    return notified_message_contexts


class NoMessageException(Exception):
    pass


def log_notification(
    notification_account_obj: models.NotificationAccount,
    cost: "CostType",
    to: User,
    notified_message_contexts: list[models.NotifiedMessageContext],
) -> models.Notification:
    notification = models.Notification(
        notification_account=notification_account_obj,
    )
    notification.set_pricing(base_cost=cost)
    notification.to_user = to
    notification.save()
    for i in notified_message_contexts:
        i.notification = notification
        i.save()
    return notification
