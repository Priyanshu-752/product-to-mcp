from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from product_to_mcp.actions.executor import ActionExecutor
from product_to_mcp.config import Settings
from product_to_mcp.domain.models import ActionToolManifest
from product_to_mcp.gateway.executor import UpstreamExecutor
from product_to_mcp.storage.secrets import PrototypeSecretStore


class MCPGateway:
    def __init__(self, store: Any, secrets: PrototypeSecretStore, settings: Settings) -> None:
        self.store = store
        self.executor = UpstreamExecutor(
            secrets, timeout=settings.upstream_timeout_seconds,
            max_response_bytes=settings.max_upstream_response_bytes,
        )
        self.action_executor = ActionExecutor(self.executor, settings.action_timeout_seconds)

    async def handle_post(self, deployment_slug: str, request: Request) -> Response:
        try:
            message = await request.json()
        except Exception:
            return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Invalid JSON."}}, status_code=400)
        if not isinstance(message, dict):
            return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "A JSON-RPC object is required."}}, status_code=400)
        method = message.get("method")
        request_id = message.get("id")
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return Response(status_code=202)
        try:
            release = self.store.release(deployment_slug=deployment_slug)
            project = self.store.project(release.project_id)
        except KeyError:
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32004, "message": "MCP deployment not found."}}, status_code=404)
        if method == "initialize":
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": project.name, "version": release.manifest_hash[:12]}}})
        if method == "tools/list":
            tools = []
            for tool in release.tools:
                value: dict[str, Any] = {
                    "name": tool.name,
                    "title": tool.title or tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_schema,
                    "outputSchema": _output_envelope_schema(tool.output_schema) if isinstance(tool, ActionToolManifest) else _legacy_output_schema(tool.output_schema),
                    "annotations": tool.annotations.model_dump(mode="json", by_alias=True, exclude_none=True),
                }
                if isinstance(tool, ActionToolManifest):
                    value.update({
                        "title": tool.title,
                        "outputSchema": _output_envelope_schema(tool.output_schema),
                    })
                tools.append(value)
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"tools": tools}})
        if method == "tools/call":
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            name = params.get("name")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            tool = next((item for item in release.tools if item.name == name), None)
            if tool is None:
                return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Tool is not enabled in this release."}}, status_code=400)
            if isinstance(tool, ActionToolManifest):
                result = await self.action_executor.call(project, tool, arguments)
            else:
                properties = tool.input_schema.get("properties", {})
                required = tool.input_schema.get("required", [])
                if not all(item in arguments for item in required) or any(item not in properties for item in arguments):
                    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Tool arguments do not match the generated schema."}}, status_code=400)
                result = await self.executor.call(project, tool, arguments)
            public_result = {key: value for key, value in result.items() if key != "trace"}
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"isError": not result["ok"], "content": [{"type": "text", "text": json.dumps(public_result, default=str)}], "structuredContent": public_result}})
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Unsupported MCP method: {method}"}}, status_code=400)

    async def handle_get(self, deployment_slug: str) -> Response:
        try:
            self.store.release(deployment_slug=deployment_slug)
        except KeyError:
            return PlainTextResponse("MCP deployment not found.", status_code=404)
        return PlainTextResponse(": product-to-mcp MCP endpoint ready\n\n", media_type="text/event-stream")


def _output_envelope_schema(data_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "status": {"enum": ["success", "rejected", "failed", "partial_success", "outcome_unknown"]},
            "retry_safe": {"type": "boolean"},
            "data": data_schema,
            "error": {},
            "failed_step": {"type": "string"},
            "write_may_have_completed": {"type": "boolean"},
            "retry_after": {"type": ["string", "null"]},
        },
        "required": ["ok", "status", "retry_safe"],
        "additionalProperties": False,
    }


def _legacy_output_schema(data_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "ok": {"type": "boolean"},
            "status_code": {"type": ["integer", "null"]},
            "data": data_schema,
            "error": {},
            "retry_after": {"type": ["string", "null"]},
            "outcome_unknown": {"type": "boolean"},
        },
        "required": ["ok"],
        "additionalProperties": True,
    }
