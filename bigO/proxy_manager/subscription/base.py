import abc

import pydantic


class BaseSubscriptionPlanProvider(abc.ABC):
    ProviderArgsModel: pydantic.BaseModel | None
    PlanArgsModel: pydantic.BaseModel | None
    TYPE_IDENTIFIER: str

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
