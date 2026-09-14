from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def now() -> datetime:
    return datetime.now(UTC)


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    name: str
    base_url: str
    auth_type: Literal["none", "bearer", "api_key"] = "none"
    api_key_header: str = "Authorization"
    created_at: datetime


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    tool_name: str
    method: Literal["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    path: str
    description: str
    input_schema: dict[str, Any]
    tags: tuple[str, ...] = ()
    default_group: str = "General"
    output_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    operation_fingerprint: str = ""
    supported: bool = True
    reason: str | None = None


class ToolAnnotations(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title: str | None = None
    read_only_hint: bool = Field(default=False, alias="readOnlyHint")
    destructive_hint: bool = Field(default=True, alias="destructiveHint")
    idempotent_hint: bool = Field(default=False, alias="idempotentHint")
    open_world_hint: bool = Field(default=True, alias="openWorldHint")


class ValueReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["action_input", "previous_step", "constant"]
    source_path: str | None = None
    source_step_id: str | None = None
    constant_value: Any = None


class ArgumentBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_path: str = Field(min_length=1)
    value: ValueReference


class StepCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: ValueReference
    operator: Literal[
        "equals", "not_equals", "exists", "not_exists", "empty", "not_empty",
        "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal",
    ]
    right: ValueReference | None = None
    on_false: Literal["skip", "fail"] = "skip"
    failure_message: str = "Action condition was not satisfied."


class ActionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    operation_id: str
    argument_bindings: tuple[ArgumentBinding, ...] = ()
    condition: StepCondition | None = None


class OutputBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_path: str = Field(min_length=1)
    value: ValueReference


class OperationGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0
    hidden: bool = False
    operation_ids: tuple[str, ...] = ()
    created_at: datetime
    updated_at: datetime


class ActionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    project_id: str
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1_000)
    group_id: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}, "additionalProperties": False})
    output_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    steps: tuple[ActionStep, ...]
    output_bindings: tuple[OutputBinding, ...] = ()
    annotations: ToolAnnotations = Field(default_factory=ToolAnnotations)
    status: Literal["draft", "valid", "approved"] = "draft"
    created_at: datetime
    updated_at: datetime


class ToolProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    project_id: str
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1_000)
    action_ids: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


class ToolManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["legacy"] = "legacy"
    operation_id: str
    name: str
    title: str | None = None
    description: str
    method: Literal["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    annotations: ToolAnnotations = Field(default_factory=ToolAnnotations)


class ActionToolManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["action"]
    action_id: str
    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    annotations: ToolAnnotations
    steps: tuple[ActionStep, ...]
    output_bindings: tuple[OutputBinding, ...]
    operations: tuple[Operation, ...]


class Release(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_id: str
    deployment_slug: str
    project_id: str
    profile_id: str | None = None
    manifest_hash: str
    tools: tuple[ToolManifest | ActionToolManifest, ...]
    created_at: datetime
