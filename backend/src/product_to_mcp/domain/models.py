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
    supported: bool = True
    reason: str | None = None


class ToolManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    name: str
    description: str
    method: Literal["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    input_schema: dict[str, Any]


class Release(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release_id: str
    deployment_slug: str
    project_id: str
    manifest_hash: str
    tools: tuple[ToolManifest, ...]
    created_at: datetime
