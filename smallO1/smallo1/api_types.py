from typing import List, Optional
import pydantic


class ProgramResponse(pydantic.BaseModel):
    outer_binary_identifier: Optional[str] = None
    inner_binary_path: Optional[str] = None

    @pydantic.model_validator(mode="before")
    def check_either_outer_binary_identifier_or_inner_binary_path(cls, values):
        if not values.get("outer_binary_identifier") and not values.get("inner_binary_path"):
            raise ValueError("Either 'outer_binary_identifier' or 'outer_binary_identifier' must be provided.")
        return values


class ConfigResponse(pydantic.BaseModel):
    id: str
    program: ProgramResponse
    run_opts: str
    configfile_content: str
    hash: str


class BaseSyncResponse(pydantic.BaseModel):
    configs: List[ConfigResponse]
