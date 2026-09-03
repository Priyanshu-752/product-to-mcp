from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from product_to_mcp.gateway.executor import UpstreamExecutor
from product_to_mcp.storage.secrets import PrototypeSecretStore
from product_to_mcp.storage.sqlite import SQLiteStore


class MCPGateway:
    def __init__(self, store: SQLiteStore, secrets: PrototypeSecretStore) -> None:
        self.store = store
        self.executor = UpstreamExecutor(secrets)

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
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"tools": [{"name": tool.name, "description": tool.description, "inputSchema": tool.input_schema} for tool in release.tools]}})
        if method == "tools/call":
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            name = params.get("name")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            tool = next((item for item in release.tools if item.name == name), None)
            if tool is None:
                return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Tool is not enabled in this release."}}, status_code=400)
            properties = tool.input_schema.get("properties", {})
            required = tool.input_schema.get("required", [])
            if not all(item in arguments for item in required) or any(item not in properties for item in arguments):
                return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": "Tool arguments do not match the generated schema."}}, status_code=400)
            result = await self.executor.call(project, tool, arguments)
            return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": {"isError": not result["ok"], "content": [{"type": "text", "text": json.dumps(result, default=str)}], "structuredContent": result}})
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Unsupported MCP method: {method}"}}, status_code=400)

    async def handle_get(self, deployment_slug: str) -> Response:
        try:
            self.store.release(deployment_slug=deployment_slug)
        except KeyError:
            return PlainTextResponse("MCP deployment not found.", status_code=404)
        return PlainTextResponse(": product-to-mcp MCP endpoint ready\n\n", media_type="text/event-stream")
