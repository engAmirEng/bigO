import abc
import enum
from typing import TypeVar

import pydantic

A = TypeVar("A", bound=pydantic.BaseModel)


class RecordType(enum.StrEnum):
    A = "A"
    AAAA = "AAAA"
    CNAME = "CNAME"
    TXT = "TXT"


class BaseDNSProvider(abc.ABC):
    ProviderArgsModel: A
    TYPE_IDENTIFIER: str

    def __init__(self, args: dict):
        self.args: A = self.ProviderArgsModel(**args)

    @abc.abstractmethod
    async def verify(self) -> None:
        ...

    @abc.abstractmethod
    async def create_record(
        self,
        base_domain_name: str,
        name: str,
        content: str,
        type: RecordType,
        comment: str | None = None,
        proxied: bool | None = None,
    ) -> str:
        ...

    @abc.abstractmethod
    async def update_record(
        self,
        record_id: str,
        base_domain_name: str,
        name: str,
        content: str,
        type: RecordType,
        comment: str | None = None,
        proxied: bool | None = None,
    ):
        ...

    @abc.abstractmethod
    async def get_record_id(self, base_domain_name: str, name: str):
        ...

    @abc.abstractmethod
    async def delete_record(self, base_domain_name: str, record_id: str):
        ...
