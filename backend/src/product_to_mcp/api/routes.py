from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, HttpUrl

from product_to_mcp.compiler.manifest import compile_tools
from product_to_mcp.domain.errors import ProductToMcpError
from product_to_mcp.domain.models import Operation
from product_to_mcp.openapi.operations import discover_operations
from product_to_mcp.openapi.parser import parse_document
from product_to_mcp.smithery.publisher import SmitheryPublisher


def public_mcp_url(request: Request, deployment_slug: str) -> str:
    return f"{request.app.state.settings.public_base_url.rstrip('/')}/mcp/{deployment_slug}/mcp"


def release_response(request: Request, release: Any) -> dict[str, Any]:
    data = release.model_dump(mode="json")
    data["mcp_url"] = public_mcp_url(request, release.deployment_slug)
    return data


class CreateProjectBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: HttpUrl
    auth_type: str = Field(default="none", pattern="^(none|bearer|api_key)$")
    api_key_header: str = Field(default="Authorization", min_length=1, max_length=80)
    upstream_api_key: str | None = Field(default=None, max_length=4_000)


class SelectionBody(BaseModel):
    operation_ids: tuple[str, ...] = ()


class PublishBody(BaseModel):
    namespace: str = Field(min_length=1, max_length=120)
    server_name: str = Field(min_length=1, max_length=120)
    smithery_api_key: str = Field(min_length=1, max_length=4_000)


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
            request.app.state.store.save_source(project_id, document, operations)
            return {"project_id": project_id, "operations": [item.model_dump(mode="json") for item in operations]}
        except KeyError as error:
            raise HTTPException(404, "Project not found.") from error
        except (ValueError, ProductToMcpError) as error:
            raise HTTPException(400, str(error)) from error

    @router.get("/projects/{project_id}/operations")
    async def list_operations(project_id: str, request: Request):
        try:
            _, operations, selected = request.app.state.store.source(project_id)
            return {"operations": [item.model_dump(mode="json") for item in operations], "selected": selected}
        except KeyError as error:
            raise HTTPException(404, "OpenAPI source not found.") from error

    @router.put("/projects/{project_id}/operations")
    async def select_operations(project_id: str, body: SelectionBody, request: Request):
        try:
            operations = request.app.state.store.select_operations(project_id, body.operation_ids)
            return {"selected": [item.operation_id for item in operations]}
        except KeyError as error:
            raise HTTPException(404, "OpenAPI source not found.") from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.post("/projects/{project_id}/releases")
    async def create_release(project_id: str, request: Request):
        try:
            _, operations, selected = request.app.state.store.source(project_id)
            tools = compile_tools(operations, selected)
            release = request.app.state.store.create_release(project_id, tools)
            return release_response(request, release)
        except KeyError as error:
            raise HTTPException(404, "OpenAPI source not found.") from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    @router.get("/releases/{release_id}")
    async def get_release(release_id: str, request: Request):
        try:
            release = request.app.state.store.release(release_id=release_id)
            return release_response(request, release)
        except KeyError as error:
            raise HTTPException(404, "Release not found.") from error

    @router.post("/releases/{release_id}/test")
    async def test_release(release_id: str, request: Request, body: dict[str, Any]):
        try:
            release = request.app.state.store.release(release_id=release_id)
            project = request.app.state.store.project(release.project_id)
            name = body.get("tool_name")
            tool = next(item for item in release.tools if item.name == name)
            result = await request.app.state.gateway.executor.call(project, tool, body.get("arguments") or {})
            return {"tool_name": name, "result": result}
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
            result = await publisher.publish(api_key=body.smithery_api_key, qualified_name=f"{body.namespace}/{body.server_name}", mcp_url=mcp_url)
            return {"mcp_url": mcp_url, "smithery": result}
        except ValueError as error:
            raise HTTPException(400, str(error)) from error

    return router
