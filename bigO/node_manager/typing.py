import enum
import pathlib
from typing import Annotated, Any, Literal, TypedDict

import pydantic


class TelegrafMetric(pydantic.BaseModel):
    fields: dict[str, Any]
    name: str
    tags: dict[str, str]
    timestamp: int


class TelegrafJsonOutPut(pydantic.BaseModel):
    metrics: list[TelegrafMetric]


class GoingtoXrayRawTrafficV1Stat(pydantic.BaseModel):
    name: str
    value: int


class GoingtoXrayRawTrafficV1JsonOutPut(pydantic.BaseModel):
    stats: list[GoingtoXrayRawTrafficV1Stat]


class XrayObservatoryResult(pydantic.BaseModel):
    alive: bool | None = None
    delay: int  # millisecond
    last_error_reason: str | None = None
    outbound_tag: str
    last_try_time: int
    last_seen_time: int | None = None


class GoingtoXrayRawMetricsV1JsonOutPut(pydantic.BaseModel):
    observatory: dict[str, XrayObservatoryResult] | None = None
    #  cmdline
    #  memstats
    #  stats {inbound, outbound, user}


class LokiStram(TypedDict):
    stream: dict[str, str]
    values: list[list[str, str]]


class MetricSchema(pydantic.BaseModel):
    ip_a: Annotated[
        str,
        pydantic.StringConstraints(min_length=1),
    ]


class SupervisorProcessStates(enum.IntEnum):
    STOPPED = 0
    STARTING = 10
    RUNNING = 20
    BACKOFF = 30
    STOPPING = 40
    EXITED = 100
    FATAL = 200
    UNKNOWN = 1000


class SupervisorProcessInfoSchema(pydantic.BaseModel):
    name: str
    group: str
    description: str
    start: int
    stop: int
    now: int
    state: SupervisorProcessStates
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


class FileSchema(pydantic.BaseModel):
    dest_path: pathlib.Path
    content: str | None = None
    url: pydantic.HttpUrl | None = None
    permission: int
    hash: str | None = None


class UrlSpec(pydantic.BaseModel):
    url: pydantic.HttpUrl
    proxy_url: pydantic.AnyUrl | Literal[""] | None = None
    weight: int


class ConfigSchema(pydantic.BaseModel):
    sync_url: pydantic.HttpUrl | Literal[""] | None = None
    sync_urls: list[UrlSpec] | None = None
    api_key: str
    interval_sec: int
    working_dir: pathlib.Path
    is_dev: bool
    sentry_dsn: pydantic.HttpUrl | None
    full_control_supervisord: bool
    supervisor_base_config_path: str = ""
    safe_stats_size: int | None = None
    each_collection_size: int | None = None
