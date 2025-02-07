from typing import Any, TypedDict

from pydantic import BaseModel


class TelegrafMetric(BaseModel):
    fields: dict[str, Any]
    name: str
    tags: dict[str, str]
    timestamp: int


class TelegrafJsonOutPut(BaseModel):
    metrics: list[TelegrafMetric]


class LokiStram(TypedDict):
    stream: dict[str, str]
    values: list[list[str, str]]
