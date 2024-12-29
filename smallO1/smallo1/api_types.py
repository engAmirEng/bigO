from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Union
import pydantic


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
    extension: Union[str, None]
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
    hash: str
    dependant_files: List[ConfigDependantFileResponse]
    _processed_run_opts: Optional[int]

    def process_run_opts(self):
        processed_run_opts = self.new_run_opts
        for i in self.dependant_files:
            assert i._dest_path
            processed_run_opts = processed_run_opts.replace(f"*#path:{i.key}#*", str(i._dest_path.absolute()))
        self._processed_run_opts = processed_run_opts


class BaseSyncResponse(pydantic.BaseModel):
    configs: List[ConfigResponse]


class MetricRequest(pydantic.BaseModel):
    ip_a: str

class BaseSyncRequest(pydantic.BaseModel):
    metrics: MetricRequest
