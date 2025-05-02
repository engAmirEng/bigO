from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pydantic
import typing_extensions


class ProgramResponse(pydantic.BaseModel):
    program_version_id: str
    outer_binary_identifier: Optional[str] = None
    inner_binary_path: Optional[str] = None

    @pydantic.model_validator(mode="before")
    def check_either_outer_binary_identifier_or_inner_binary_path(cls, values):
        if not values.get("outer_binary_identifier") and not values.get("inner_binary_path"):
            raise ValueError("Either 'outer_binary_identifier' or 'outer_binary_identifier' must be provided.")
        return values


class ConfigDependantFileResponse(pydantic.BaseModel):
    key: str
    content: str
    extension: Optional[str]
    hash: str
    _processed_content: Optional[str]
    _dest_path: Optional[Path]

    def set_dest(self, path: Path):
        self._dest_path = path

    def process_content(self, other_deps: List[ConfigDependantFileResponse]):
        content = self.content
        for i in other_deps:
            content = content.replace(f"*#path:{i.key}#*", str(i._dest_path.absolute()))
        self._processed_content = content


class ConfigResponse(pydantic.BaseModel):
    id: str
    program: ProgramResponse
    new_run_opts: str
    comma_separated_environment: Optional[str] = None
    hash: str
    dependant_files: List[ConfigDependantFileResponse]
    _processed_run_opts: Optional[int]
    _processed_comma_separated_environment: Optional[int]

    def process_run_opts(self, deps: List[ConfigDependantFileResponse]):
        processed_run_opts = self.new_run_opts
        for i in deps:
            assert i._dest_path
            processed_run_opts = processed_run_opts.replace(f"*#path:{i.key}#*", str(i._dest_path.absolute()))
            processed_run_opts = processed_run_opts.replace(f"*#dir:{i.key}#*", str(i._dest_path.absolute().parent))
        self._processed_run_opts = processed_run_opts

    def process_comma_separated_environment(self, deps: List[ConfigDependantFileResponse]):
        processed_comma_separated_environment = self.comma_separated_environment
        for i in deps:
            assert i._dest_path
            processed_comma_separated_environment = processed_comma_separated_environment.replace(f"*#path:{i.key}#*", str(i._dest_path.absolute()))
            processed_comma_separated_environment = processed_comma_separated_environment.replace(f"*#dir:{i.key}#*", str(i._dest_path.absolute().parent))
        self._processed_comma_separated_environment = processed_comma_separated_environment


class BaseSyncResponse(pydantic.BaseModel):
    configs: List[ConfigResponse]
    global_deps: List[ConfigDependantFileResponse]


class MetricRequest(pydantic.BaseModel):
    ip_a: str

class ConfigStateRequest(pydantic.BaseModel):
    time: pydantic.AwareDatetime
    supervisorprocessinfo: "SupervisorProcessInfoDict"
    stdout: "SupervisorProcessTailLog"
    stderr: "SupervisorProcessTailLog"

class BaseSyncRequest(pydantic.BaseModel):
    metrics: MetricRequest
    configs_states: Optional[List[ConfigStateRequest]]
    smallo1_logs: "SupervisorProcessTailLog"

class SupervisorProcessInfoDict(typing_extensions.TypedDict):
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

class SupervisorProcessTailLog(pydantic.BaseModel):
    bytes: str
    offset: int
    overflow: bool
