import abc
from typing import TYPE_CHECKING, Generic, TypeVar

import pydantic
from moneyed import Money

from bigO.users.models import User
from django.db.models import QuerySet

if TYPE_CHECKING:
    from .. import models

ProviderArgsT = TypeVar("ProviderArgsT", bound=pydantic.BaseModel | None)
PlanArgsT = TypeVar("PlanArgsT", bound=pydantic.BaseModel | None)


class BasePaymentProvider(abc.ABC, Generic[ProviderArgsT, PlanArgsT]):
    ProviderArgsModel: type[ProviderArgsT]
    PaymentArgsModel: type[PlanArgsT]
    TYPE_IDENTIFIER: str

    def __init__(self, args: ProviderArgsT):
        self.provider_args = args

    @classmethod
    @abc.abstractmethod
    def get_price(cls, identifier: str, price: Money, provider_args: PlanArgsT | None):
        ...

    @classmethod
    @abc.abstractmethod
    async def pend(cls, admins: QuerySet[User], payment: "models.Payment"):
        ...
