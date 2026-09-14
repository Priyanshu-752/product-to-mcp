from __future__ import annotations

import re
import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, HttpUrl, field_validator

from product_to_mcp.actions.validation import derived_annotations, validate_action
from product_to_mcp.compiler.manifest import compile_actions, compile_tools
from product_to_mcp.domain.errors import ProductToMcpError
from product_to_mcp.domain.models import (
    ActionDefinition, ActionStep, ActionToolManifest, ArgumentBinding, Operation, OperationGroup,
    OutputBinding, ToolManifest, ToolProfile, ValueReference, now,
)
from product_to_mcp.openapi.operations import discover_operations
from product_to_mcp.openapi.parser import parse_document
from product_to_mcp.openapi.toolsets import available_toolsets, resolve_toolset_operations
from product_to_mcp.smithery.publisher import SmitheryPublisher


def public_mcp_url(request: Request, deployment_slug: str) -> str:
    return f"{request.app.state.settings.public_base_url.rstrip('/')}/mcp/{deployment_slug}/mcp"


def release_response(request: Request, release: Any) -> dict[str, Any]:
    data = release.model_dump(mode="json", by_alias=True)
    data["mcp_url"] = public_mcp_url(request, release.deployment_slug)
    api_tool_count = sum(getattr(tool, "kind", "legacy") != "action" for tool in release.tools)
    action_tool_count = len(release.tools) - api_tool_count
    data["tool_counts"] = {"api": api_tool_count, "actions": action_tool_count, "total": len(release.tools)}
    data["tool_mode"] = "api_and_actions" if api_tool_count and action_tool_count else "actions_only" if action_tool_count else "api_only"
    return data


class CreateProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: HttpUrl
    auth_type: str = Field(default="none", pattern="^(none|bearer|api_key)$")
    api_key_header: str = Field(default="Authorization", min_length=1, max_length=80)
    upstream_api_key: str | None = Field(default=None, max_length=4_000)


class SelectionBody(BaseModel):
    operation_ids: tuple[str, ...] = ()


class GroupInput(BaseModel):
    group_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    hidden: bool = False
    operation_ids: tuple[str, ...] = ()


class GroupsBody(BaseModel):
    groups: tuple[GroupInput, ...]


class CustomToolsetBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    operation_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def non_blank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Toolset name cannot be blank.")
        return value.strip()


class CreateActionBody(BaseModel):
    operation_ids: tuple[str, ...] = Field(min_length=1, max_length=10)
    name: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=1_000)
    group_id: str | None = None


class UpdateActionBody(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1_000)
    group_id: str | None = None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    steps: tuple[ActionStep, ...]
    output_bindings: tuple[OutputBinding, ...] = ()


class ProfileBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1_000)
    action_ids: tuple[str, ...] = Field(min_length=1)


class ReleaseBody(BaseModel):
    profile_id: str | None = None
    tool_mode: Literal["api_and_actions", "actions_only", "api_only"] = "api_and_actions"
    confirm_large_profile: bool = False
    selected_toolset_ids: tuple[str, ...] | None = None


class PublishBody(BaseModel):
    namespace: str = Field(min_length=1, max_length=120)
    server_name: str = Field(min_length=1, max_length=120)
    smithery_api_key: str = Field(min_length=1, max_length=4_000)
    display_name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1_000)
    homepage: HttpUrl
    icon_url: HttpUrl
    repository_url: HttpUrl | None = None
    license: str | None = Field(default=None, max_length=120)
    unlisted: bool = False

    @field_validator("namespace", "server_name", "smithery_api_key", "display_name", "description", "license")
    @classmethod
    def non_blank_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Field cannot be blank.")
        return trimmed


def create_router() -> APIRouter:
    router = APIRouter(prefix="/v1")

    @router.get("/projects")
    async def list_projects(request: Request):
        return {"projects": [item.model_dump(mode="json") for item in request.app.state.store.list_projects()]}

    @router.post("/projects")
    async def create_project(body: CreateProjectBody, request: Request):
        project = request.app.state.store.create_project(body.name, str(body.base_url), body.auth_type, body.api_key_header)
        request.app.state.secrets.put(project.project_id, body.upstream_api_key)
        return project

    @router.get("/projects/{project_id}")
    async def get_project(project_id: str, request: Request):
        try:
            return request.app.state.store.project(project_id)
        except KeyError as error:
            raise HTTPException(404, "Project not found.") from error

    @router.post("/projects/{project_id}/openapi")
    async def upload_openapi(project_id: str, request: Request, file: Annotated[UploadFile | None, File()] = None, content: Annotated[str | None, Form()] = None):
        try:
            request.app.state.store.project(project_id)
            raw = await file.read(request.app.state.settings.max_openapi_bytes + 1) if file else (content or "").encode()
            if len(raw) > request.app.state.settings.max_openapi_bytes:
                raise ValueError("OpenAPI document is too large.")
            document = parse_document(raw)
            operations = discover_operations(document)
            try:
                _, previous, _ = request.app.state.store.source(project_id)
            except KeyError:
                previous = ()
            old = {item.operation_id: item.operation_fingerprint for item in previous}
            new = {item.operation_id: item.operation_fingerprint for item in operations}
            changed = {item for item in old if item not in new or old[item] != new[item]}
            request.app.state.store.save_source(project_id, document, operations)
            groups = request.app.state.store.sync_groups(project_id, operations)
            invalidated = request.app.state.store.invalidate_actions(project_id, changed)
            return {"project_id": project_id, "operations": _dump(operations), "groups": _dump(groups), "toolsets": available_toolsets(operations, request.app.state.store.list_custom_toolsets(project_id)), "invalidated_action_ids": invalidated}
        except KeyError as error:
            raise HTTPException(404, "Project not found.") from error
        except (ValueError, ProductToMcpError) as error:
            raise HTTPException(400, str(error)) from error

    @router.get("/projects/{project_id}/workspace")
    async def workspace(project_id: str, request: Request):
        try:
            project = request.app.state.store.project(project_id)
            _, operations, _ = request.app.state.store.source(project_id)
            groups = request.app.state.store.sync_groups(project_id, operations)
            return {
                "project": project.model_dump(mode="json"), "operations": _dump(operations), "groups": _dump(groups), "toolsets": available_toolsets(operations, request.app.state.store.list_custom_toolsets(project_id)),
                "actions": _dump(request.app.state.store.list_actions(project_id), aliases=True),
                "profiles": _dump(request.app.state.store.list_profiles(project_id)),
                "limits": {"max_chain_steps": request.app.state.settings.max_chain_steps, "warn_chain_steps": 5, "warn_profile_tools": 20, "confirm_profile_tools": 30},
            }
        except KeyError as error:
            raise HTTPException(404, "Project or OpenAPI source not found.") from error

    @router.get("/projects/{project_id}/operations")
    async def list_operations(project_id: str, request: Request):
        try:
            _, operations, selected = request.app.state.store.source(project_id)
            return {"operations": _dump(operations), "selected": selected}
        except KeyError as error:
            raise HTTPException(404, "OpenAPI source not found.") from error

    @router.put("/projects/{project_id}/operations")
    async def select_operations(project_id: str, body: SelectionBody, request: Request):
        try:
            return {"selected": [item.operation_id for item in request.app.state.store.select_operations(project_id, body.operation_ids)]}
        except KeyError as error:
            raise HTTPException(404, "OpenAPI source not found.") from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.get("/projects/{project_id}/groups")
    async def list_groups(project_id: str, request: Request):
        return {"groups": _dump(request.app.state.store.list_groups(project_id))}

    def save_custom_toolset(request: Request, project_id: str, body: CustomToolsetBody, toolset_id: str | None = None):
        try:
            _, operations, _ = request.app.state.store.source(project_id)
            existing = request.app.state.store.list_custom_toolsets(project_id)
            if toolset_id is not None and not any(item["toolset_id"] == toolset_id for item in existing):
                raise HTTPException(404, "Custom toolset not found.")
            if any(item["name"].casefold() == body.name.casefold() and item["toolset_id"] != toolset_id for item in existing):
                raise ValueError("A custom toolset with this name already exists.")
            if any(item["name"].casefold() == body.name.casefold() for item in available_toolsets(operations, ())):
                raise ValueError("A toolset with this name is already generated from OpenAPI. Choose another name.")
            if len(body.operation_ids) != len(set(body.operation_ids)):
                raise ValueError("Custom toolset operations must be unique.")
            supported = {item.operation_id for item in operations if item.supported}
            if any(item not in supported for item in body.operation_ids):
                raise ValueError("Select only supported operations from the current OpenAPI source.")
            saved_id = toolset_id or f"custom_{secrets.token_hex(8)}"
            request.app.state.store.save_custom_toolset(project_id, saved_id, body.name, body.operation_ids)
            return next(item for item in available_toolsets(operations, request.app.state.store.list_custom_toolsets(project_id)) if item["toolset_id"] == saved_id)
        except KeyError as error:
            raise HTTPException(404, "OpenAPI source not found.") from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.post("/projects/{project_id}/custom-toolsets")
    async def create_custom_toolset(project_id: str, body: CustomToolsetBody, request: Request):
        return save_custom_toolset(request, project_id, body)

    @router.put("/projects/{project_id}/custom-toolsets/{toolset_id}")
    async def update_custom_toolset(project_id: str, toolset_id: str, body: CustomToolsetBody, request: Request):
        return save_custom_toolset(request, project_id, body, toolset_id)

    @router.delete("/projects/{project_id}/custom-toolsets/{toolset_id}", status_code=204)
    async def delete_custom_toolset(project_id: str, toolset_id: str, request: Request):
        try:
            request.app.state.store.delete_custom_toolset(project_id, toolset_id)
        except KeyError as error:
            raise HTTPException(404, "Custom toolset not found.") from error

    @router.put("/projects/{project_id}/groups", deprecated=True)
    async def replace_groups(project_id: str, body: GroupsBody, request: Request):
        try:
            _, operations, _ = request.app.state.store.source(project_id)
            supported = {item.operation_id for item in operations if item.supported}
            assigned = [operation_id for group in body.groups for operation_id in group.operation_ids]
            if len(assigned) != len(set(assigned)) or set(assigned) != supported:
                raise ValueError("Every supported operation must be assigned to exactly one group.")
            existing = {item.group_id: item for item in request.app.state.store.list_groups(project_id)}
            stamp = now()
            groups = tuple(OperationGroup(
                group_id=item.group_id or f"grp_{secrets.token_urlsafe(8)}", project_id=project_id,
                name=item.name.strip(), sort_order=index, hidden=item.hidden, operation_ids=item.operation_ids,
                created_at=existing[item.group_id].created_at if item.group_id in existing else stamp, updated_at=stamp,
            ) for index, item in enumerate(body.groups))
            return {"groups": _dump(request.app.state.store.replace_groups(project_id, groups))}
        except KeyError as error:
            raise HTTPException(404, "OpenAPI source not found.") from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.get("/projects/{project_id}/actions")
    async def list_actions(project_id: str, request: Request):
        return {"actions": _dump(request.app.state.store.list_actions(project_id), aliases=True)}

    @router.post("/projects/{project_id}/actions")
    async def create_action(project_id: str, body: CreateActionBody, request: Request):
        try:
            _, operations, _ = request.app.state.store.source(project_id)
            by_id = {item.operation_id: item for item in operations if item.supported}
            if any(item not in by_id for item in body.operation_ids):
                raise ValueError("An action references an unavailable operation.")
            action = _default_action(project_id, tuple(by_id[item] for item in body.operation_ids), body)
            if body.name is None:
                name = _available_action_name(request.app.state.store, action, operations)
                updates: dict[str, Any] = {"name": name}
                if body.title is None:
                    updates["title"] = _title(name)
                action = action.model_copy(update=updates)
            _ensure_action_name_unique(request.app.state.store, action)
            request.app.state.store.save_action(action)
            return action.model_dump(mode="json", by_alias=True)
        except KeyError as error:
            raise HTTPException(404, "OpenAPI source not found.") from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.get("/projects/{project_id}/actions/{action_id}")
    async def get_action(project_id: str, action_id: str, request: Request):
        return _owned_action(request.app.state.store, project_id, action_id).model_dump(mode="json", by_alias=True)

    @router.put("/projects/{project_id}/actions/{action_id}")
    async def update_action(project_id: str, action_id: str, body: UpdateActionBody, request: Request):
        existing = _owned_action(request.app.state.store, project_id, action_id)
        action = ActionDefinition(
            action_id=existing.action_id, project_id=project_id, name=body.name, title=body.title,
            description=body.description, group_id=body.group_id, input_schema=body.input_schema,
            output_schema=body.output_schema, steps=body.steps, output_bindings=body.output_bindings,
            annotations=existing.annotations, status="draft", created_at=existing.created_at, updated_at=now(),
        )
        _ensure_action_name_unique(request.app.state.store, action)
        request.app.state.store.save_action(action)
        return action.model_dump(mode="json", by_alias=True)

    @router.delete("/projects/{project_id}/actions/{action_id}", status_code=204)
    async def delete_action(project_id: str, action_id: str, request: Request):
        _owned_action(request.app.state.store, project_id, action_id)
        if any(action_id in profile.action_ids for profile in request.app.state.store.list_profiles(project_id)):
            raise HTTPException(409, "Remove this action from its profiles before deleting it.")
        request.app.state.store.delete_action(action_id)

    @router.post("/projects/{project_id}/actions/{action_id}/validate")
    async def validate_saved_action(project_id: str, action_id: str, request: Request):
        action = _owned_action(request.app.state.store, project_id, action_id)
        _, operations, _ = request.app.state.store.source(project_id)
        errors = validate_action(action, operations, request.app.state.settings.max_chain_steps)
        action = action.model_copy(update={"status": "valid" if not errors else "draft", "updated_at": now(), "annotations": derived_annotations(action, {item.operation_id: item for item in operations})})
        request.app.state.store.save_action(action)
        return {"valid": not errors, "errors": errors, "action": action.model_dump(mode="json", by_alias=True)}

    @router.post("/projects/{project_id}/actions/{action_id}/approve")
    async def approve_action(project_id: str, action_id: str, request: Request):
        action = _owned_action(request.app.state.store, project_id, action_id)
        _, operations, _ = request.app.state.store.source(project_id)
        errors = validate_action(action, operations, request.app.state.settings.max_chain_steps)
        if errors:
            raise HTTPException(400, {"message": "Action validation failed.", "errors": errors})
        action = action.model_copy(update={"status": "approved", "updated_at": now(), "annotations": derived_annotations(action, {item.operation_id: item for item in operations})})
        request.app.state.store.save_action(action)
        return action.model_dump(mode="json", by_alias=True)

    @router.post("/projects/{project_id}/actions/{action_id}/test")
    async def test_action(project_id: str, action_id: str, request: Request, body: dict[str, Any]):
        action = _owned_action(request.app.state.store, project_id, action_id)
        _, operations, _ = request.app.state.store.source(project_id)
        errors = validate_action(action, operations, request.app.state.settings.max_chain_steps)
        if errors:
            raise HTTPException(400, {"message": "Action validation failed.", "errors": errors})
        tool = compile_actions((action.model_copy(update={"status": "approved"}),), operations, request.app.state.settings.max_chain_steps)[0]
        project = request.app.state.store.project(project_id)
        arguments = body["arguments"] if "arguments" in body else body
        return await request.app.state.gateway.action_executor.call(project, tool, arguments, include_trace=True)

    @router.get("/projects/{project_id}/profiles")
    async def list_profiles(project_id: str, request: Request):
        return {"profiles": _dump(request.app.state.store.list_profiles(project_id))}

    @router.post("/projects/{project_id}/profiles")
    async def create_profile(project_id: str, body: ProfileBody, request: Request):
        _validate_profile_actions(request.app.state.store, project_id, body.action_ids)
        stamp = now()
        profile = ToolProfile(profile_id=f"prf_{secrets.token_urlsafe(8)}", project_id=project_id, name=body.name.strip(), description=body.description.strip(), action_ids=body.action_ids, created_at=stamp, updated_at=stamp)
        _ensure_profile_name_unique(request.app.state.store, profile)
        request.app.state.store.save_profile(profile)
        return profile.model_dump(mode="json")

    @router.put("/projects/{project_id}/profiles/{profile_id}")
    async def update_profile(project_id: str, profile_id: str, body: ProfileBody, request: Request):
        existing = _owned_profile(request.app.state.store, project_id, profile_id)
        _validate_profile_actions(request.app.state.store, project_id, body.action_ids)
        profile = existing.model_copy(update={"name": body.name.strip(), "description": body.description.strip(), "action_ids": body.action_ids, "updated_at": now()})
        _ensure_profile_name_unique(request.app.state.store, profile)
        request.app.state.store.save_profile(profile)
        return profile.model_dump(mode="json")

    @router.delete("/projects/{project_id}/profiles/{profile_id}", status_code=204)
    async def delete_profile(project_id: str, profile_id: str, request: Request):
        _owned_profile(request.app.state.store, project_id, profile_id)
        request.app.state.store.delete_profile(profile_id)

    def release_tools(request: Request, project_id: str, body: ReleaseBody) -> tuple[ToolManifest | ActionToolManifest, ...]:
        _, operations, _ = request.app.state.store.source(project_id)
        selected_api_operation_ids = resolve_toolset_operations(operations, body.selected_toolset_ids, request.app.state.store.list_custom_toolsets(project_id))
        if body.tool_mode == "api_only":
            return compile_tools(operations, selected_api_operation_ids)
        if body.tool_mode == "actions_only" and body.selected_toolset_ids:
            raise ValueError("Actions-only releases cannot select API toolsets.")
        if body.profile_id is None:
            raise ValueError("A publishing profile is required for action tools.")
        profile = _owned_profile(request.app.state.store, project_id, body.profile_id)
        if len(profile.action_ids) > 30 and not body.confirm_large_profile:
            raise ValueError("Profiles with more than 30 tools require explicit confirmation.")
        actions = tuple(request.app.state.store.action(item) for item in profile.action_ids)
        action_tools = compile_actions(actions, operations, request.app.state.settings.max_chain_steps)
        if body.tool_mode == "actions_only":
            return action_tools
        return _combine_release_tools(compile_tools(operations, selected_api_operation_ids), action_tools)

    @router.post("/projects/{project_id}/releases/preview")
    async def preview_release(project_id: str, body: ReleaseBody, request: Request):
        try:
            tools = release_tools(request, project_id, body)
            api_count = sum(getattr(tool, "kind", "legacy") != "action" for tool in tools)
            return {"tool_names": [tool.name for tool in tools], "tool_counts": {"api": api_count, "actions": len(tools) - api_count, "total": len(tools)}}
        except KeyError as error:
            raise HTTPException(404, "OpenAPI source, action, or profile not found.") from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.post("/projects/{project_id}/releases")
    async def create_release(project_id: str, request: Request, body: ReleaseBody | None = None):
        try:
            _, operations, selected = request.app.state.store.source(project_id)
            if body is None:
                if not request.app.state.settings.allow_legacy_releases:
                    raise ValueError("A publishing profile is required.")
                release = request.app.state.store.create_release(project_id, compile_tools(operations, _selected_or_all_supported(operations, selected)))
            else:
                tools = release_tools(request, project_id, body)
                release = request.app.state.store.create_release(project_id, tools, body.profile_id if body.tool_mode != "api_only" else None)
            return release_response(request, release)
        except KeyError as error:
            raise HTTPException(404, "OpenAPI source, action, or profile not found.") from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.get("/releases/{release_id}")
    async def get_release(release_id: str, request: Request):
        try:
            return release_response(request, request.app.state.store.release(release_id=release_id))
        except KeyError as error:
            raise HTTPException(404, "Release not found.") from error

    @router.post("/releases/{release_id}/test")
    async def test_release(release_id: str, request: Request, body: dict[str, Any]):
        try:
            release = request.app.state.store.release(release_id=release_id)
            project = request.app.state.store.project(release.project_id)
            tool = next(item for item in release.tools if item.name == body.get("tool_name"))
            if getattr(tool, "kind", "legacy") == "action":
                result = await request.app.state.gateway.action_executor.call(project, tool, body.get("arguments") or {}, include_trace=True)
            else:
                result = await request.app.state.gateway.executor.call(project, tool, body.get("arguments") or {})
            return {"tool_name": tool.name, "result": result}
        except (KeyError, StopIteration) as error:
            raise HTTPException(404, "Release or tool not found.") from error

    @router.post("/releases/{release_id}/smithery/publish")
    async def publish_release(release_id: str, body: PublishBody, request: Request):
        try:
            release = request.app.state.store.release(release_id=release_id)
        except KeyError as error:
            raise HTTPException(404, "Release not found.") from error
        mcp_url = public_mcp_url(request, release.deployment_slug)
        publisher = SmitheryPublisher(request.app.state.settings.smithery_api_url)
        try:
            result = await publisher.publish(
                api_key=body.smithery_api_key,
                qualified_name=f"{body.namespace}/{body.server_name}",
                mcp_url=mcp_url,
                display_name=body.display_name,
                description=body.description,
                homepage=str(body.homepage),
                icon_url=str(body.icon_url),
                repository_url=str(body.repository_url) if body.repository_url else None,
                license=body.license,
                unlisted=body.unlisted,
            )
            return {"mcp_url": mcp_url, "smithery": result}
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    return router


def _dump(items: Any, aliases: bool = False) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json", by_alias=aliases) for item in items]


def _default_action(project_id: str, operations: tuple[Operation, ...], body: CreateActionBody) -> ActionDefinition:
    properties: dict[str, Any] = {}
    required: list[str] = []
    steps: list[ActionStep] = []
    used_step_ids: set[str] = set()
    for operation in operations:
        base = re.sub(r"[^a-z0-9_]+", "_", operation.tool_name.lower()).strip("_") or "step"
        step_id = base
        counter = 2
        while step_id in used_step_ids:
            step_id = f"{base}_{counter}"
            counter += 1
        used_step_ids.add(step_id)
        bindings: list[ArgumentBinding] = []
        operation_required = set(operation.input_schema.get("required", []))
        for argument, schema in operation.input_schema.get("properties", {}).items():
            input_name = argument
            clean_schema = {key: value for key, value in schema.items() if key != "x-location"}
            if input_name in properties and properties[input_name] != clean_schema:
                input_name = f"{step_id}_{argument}"
            properties[input_name] = clean_schema
            if argument in operation_required and input_name not in required:
                required.append(input_name)
            bindings.append(ArgumentBinding(target_path=argument, value=ValueReference(source="action_input", source_path=input_name)))
        steps.append(ActionStep(step_id=step_id, operation_id=operation.operation_id, argument_bindings=tuple(bindings)))
    name = body.name or operations[0].tool_name
    input_schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        input_schema["required"] = required
    stamp = now()
    description = body.description or _default_action_description(operations)
    return ActionDefinition(
        action_id=f"act_{secrets.token_urlsafe(8)}", project_id=project_id,
        name=name, title=body.title or _title(name),
        description=description,
        group_id=body.group_id, input_schema=input_schema, output_schema=operations[-1].output_schema,
        steps=tuple(steps), created_at=stamp, updated_at=stamp,
    )


def _default_action_description(operations: tuple[Operation, ...]) -> str:
    if len(operations) == 1:
        operation = operations[0]
        return f"Run {operation.method} {operation.path}: {operation.description}"
    names = ", ".join(operation.tool_name for operation in operations)
    return f"Run {len(operations)} approved API operations in order: {names}."


def _selected_or_all_supported(operations: tuple[Operation, ...], selected: tuple[str, ...]) -> tuple[str, ...]:
    if selected:
        return selected
    return _all_supported_operation_ids(operations)


def _all_supported_operation_ids(operations: tuple[Operation, ...]) -> tuple[str, ...]:
    return tuple(operation.operation_id for operation in operations if operation.supported)


def _combine_release_tools(api_tools: tuple[ToolManifest, ...], action_tools: tuple[ActionToolManifest, ...]) -> tuple[ToolManifest | ActionToolManifest, ...]:
    used = {tool.name for tool in api_tools}
    combined: list[ToolManifest | ActionToolManifest] = [*api_tools]
    for tool in action_tools:
        name = _available_tool_name(tool.name, used, "_action")
        used.add(name)
        if name != tool.name:
            title = tool.title if tool.title.casefold().endswith("action") else f"{tool.title} Action"
            tool = tool.model_copy(update={"name": name, "title": title})
        combined.append(tool)
    return tuple(combined)


def _available_tool_name(name: str, used: set[str], suffix: str) -> str:
    if name not in used:
        return name
    base = f"{name[:64 - len(suffix)]}{suffix}"
    candidate = base
    counter = 2
    while candidate in used:
        counter_suffix = f"_{counter}"
        candidate = f"{base[:64 - len(counter_suffix)]}{counter_suffix}"
        counter += 1
    return candidate


def _title(name: str) -> str:
    return " ".join(item.capitalize() for item in name.split("_"))


def _owned_action(store: Any, project_id: str, action_id: str) -> ActionDefinition:
    try:
        action = store.action(action_id)
    except KeyError as error:
        raise HTTPException(404, "Action not found.") from error
    if action.project_id != project_id:
        raise HTTPException(404, "Action not found.")
    return action


def _owned_profile(store: Any, project_id: str, profile_id: str) -> ToolProfile:
    try:
        profile = store.profile(profile_id)
    except KeyError as error:
        raise HTTPException(404, "Profile not found.") from error
    if profile.project_id != project_id:
        raise HTTPException(404, "Profile not found.")
    return profile


def _ensure_action_name_unique(store: Any, action: ActionDefinition) -> None:
    if any(item.name == action.name and item.action_id != action.action_id for item in store.list_actions(action.project_id)):
        raise HTTPException(400, "Action names must be unique inside a project.")


def _ensure_profile_name_unique(store: Any, profile: ToolProfile) -> None:
    if any(item.name.casefold() == profile.name.casefold() and item.profile_id != profile.profile_id for item in store.list_profiles(profile.project_id)):
        raise HTTPException(400, "Profile names must be unique inside a project.")


def _available_action_name(store: Any, action: ActionDefinition, operations: tuple[Operation, ...] = ()) -> str:
    existing = {item.name for item in store.list_actions(action.project_id)} | {item.tool_name for item in operations if item.supported}
    if action.name not in existing:
        return action.name
    suffix = "_chain" if len(action.steps) > 1 else "_action"
    base = f"{action.name[:64 - len(suffix)]}{suffix}"
    candidate = base
    counter = 2
    while candidate in existing:
        suffix = f"_{counter}"
        candidate = f"{base[:64 - len(suffix)]}{suffix}"
        counter += 1
    return candidate


def _validate_profile_actions(store: Any, project_id: str, action_ids: tuple[str, ...]) -> None:
    if len(action_ids) != len(set(action_ids)):
        raise HTTPException(400, "A profile cannot contain duplicate actions.")
    for action_id in action_ids:
        action = _owned_action(store, project_id, action_id)
        if action.status != "approved":
            raise HTTPException(400, f"Action '{action.name}' must be approved before it can be added to a profile.")
