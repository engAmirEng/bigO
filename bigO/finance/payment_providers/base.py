import abc
from typing import Generic, TypeVar

import pydantic

ProviderArgsT = TypeVar("ProviderArgsT", bound=pydantic.BaseModel | None)
PlanArgsT = TypeVar("PlanArgsT", bound=pydantic.BaseModel | None)


class BasePaymentProvider(abc.ABC, Generic[ProviderArgsT, PlanArgsT]):
    ProviderArgsModel: type[ProviderArgsT]
    PaymentArgsModel: type[PlanArgsT]
    TYPE_IDENTIFIER: str

    def __init__(self, args: ProviderArgsT):
        self.provider_args = args

    async def verify(self):
        pass
