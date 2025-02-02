from typing import Any

from pydantic import BaseModel


class TelegrafMetric(BaseModel):
    fields: dict[str, Any]
    name: str
    tags: dict[str, str]
    timestamp: int


class TelegrafJsonOutPut(BaseModel):
    metrics: list[TelegrafMetric]
