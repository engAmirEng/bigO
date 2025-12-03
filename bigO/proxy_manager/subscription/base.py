import abc
from typing import Generic, TypeVar

import pydantic
from moneyed import Currency, Money

from django.dispatch import Signal

ProviderArgsT = TypeVar("ProviderArgsT", bound=pydantic.BaseModel | None)
PlanArgsT = TypeVar("PlanArgsT", bound=pydantic.BaseModel | None)

subscription_near_end_signal = Signal()


class BaseSubscriptionPlanProvider(abc.ABC, Generic[ProviderArgsT, PlanArgsT]):
    ProviderArgsModel: type[ProviderArgsT]
    PlanArgsModel: type[PlanArgsT]
    TYPE_IDENTIFIER: str

    def __init__(self, provider_args: ProviderArgsT, plan_args: PlanArgsT, currency: Currency):
        if self.ProviderArgsModel:
            self.provider_args = self.ProviderArgsModel(**provider_args)
        else:
            self.provider_args = None
        if self.PlanArgsModel:
            self.plan_args = self.PlanArgsModel(**plan_args)
        else:
            self.plan_args = None
        self.currency = currency

    @abc.abstractmethod
    def calc_init_price(self) -> Money:
        ...

    @abc.abstractmethod
    def get_total_limit_bytes(self):
        ...

    @classmethod
    @abc.abstractmethod
    def get_expires_at_ann_expr(cls):
        ...

    @classmethod
    @abc.abstractmethod
    def get_dl_bytes_remained_expr(cls):
        ...

    @classmethod
    @abc.abstractmethod
    def get_up_bytes_remained_expr(cls):
        ...

    @classmethod
    @abc.abstractmethod
    def get_total_limit_bytes_expr(cls):
        ...
