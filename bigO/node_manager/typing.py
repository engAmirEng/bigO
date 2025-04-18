from typing import Annotated, Any, TypedDict

import pydantic


class TelegrafMetric(pydantic.BaseModel):
    fields: dict[str, Any]
    name: str
    tags: dict[str, str]
    timestamp: int


class TelegrafJsonOutPut(pydantic.BaseModel):
    metrics: list[TelegrafMetric]


class LokiStram(TypedDict):
    stream: dict[str, str]
    values: list[list[str, str]]


class MetricSchema(pydantic.BaseModel):
    ip_a: Annotated[
        str,
        pydantic.StringConstraints(min_length=1),
    ]


class SupervisorProcessInfoSchema(pydantic.BaseModel):
    name: str
    group: str
    description: str
    start: int
    stop: int
    now: int
    state: int
    statename: str
    spawnerr: str
    exitstatus: int
    stdout_logfile: str
    stderr_logfile: str
    pid: int


class SupervisorProcessTailLogSerializerSchema(pydantic.BaseModel):
    bytes: str
    offset: int
    overflow: bool


class ConfigStateSchema(pydantic.BaseModel):
    time: pydantic.AwareDatetime
    supervisorprocessinfo: SupervisorProcessInfoSchema
    stdout: SupervisorProcessTailLogSerializerSchema
    stderr: SupervisorProcessTailLogSerializerSchema
