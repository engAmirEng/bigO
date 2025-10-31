import abc
from typing import Generic, TypeVar

import pydantic

ProviderArgsT = TypeVar("ProviderArgsT", bound=pydantic.BaseModel | None)
PlanArgsT = TypeVar("PlanArgsT", bound=pydantic.BaseModel | None)


class BaseSubscriptionPlanProvider(abc.ABC, Generic[ProviderArgsT, PlanArgsT]):
    ProviderArgsModel: type[ProviderArgsT]
    PlanArgsModel: type[PlanArgsT]
    TYPE_IDENTIFIER: str

    def __init__(self, provider_args: ProviderArgsT, plan_args: PlanArgsT):
        self.provider_args = provider_args
        self.plan_args = plan_args

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
