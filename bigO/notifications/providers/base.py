import abc
from decimal import Decimal
from typing import TYPE_CHECKING, ClassVar, Union

from ...users.models import User

if TYPE_CHECKING:
    from ..models import NotificationAccount

from django.db import models
from django.utils.translation import gettext_lazy


class BaseNotificationProvider(abc.ABC):
    class Type(models.TextChoices):
        SMS = "sms", gettext_lazy("sms")
        FCM = "fcm", gettext_lazy("fcm")

    KEY: ClassVar[str]
    TITLE: ClassVar[str]
    EXTRAS_INPUT_SCHEMA: ClassVar[dict]
    TYPE: ClassVar[Type]
    account: Union["NotificationAccount", None]

    def __init__(self, account: "NotificationAccount" = None):
        self.account = account

    @classmethod
    @abc.abstractmethod
    def initialize_from_account(cls, account: "NotificationAccount"):
        ...

    @abc.abstractmethod
    def send(self, to: User, **kwargs) -> (bool, Decimal):
        ...

    @classmethod
    @abc.abstractmethod
    def get_available_send_vars(cls) -> set:
        ...

    @abc.abstractmethod
    def get_cost(self, **kwargs):
        """
        :returns real price before any profit
        """
        ...


class NotificationInput(models.TextChoices):
    BODY = "body"
    TITLE = "title"
    LINK = "link"
    ICON_URL = "icon_url"
    IMAGE_URL = "image_url"
