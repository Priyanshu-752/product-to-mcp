from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx

from product_to_mcp.domain.models import Operation, Project, ToolManifest
from product_to_mcp.storage.secrets import PrototypeSecretStore


class UpstreamExecutor:
    def __init__(self, secrets: PrototypeSecretStore, timeout: float = 20, max_response_bytes: int = 2 * 1024 * 1024, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.secrets = secrets
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        self.transport = transport

    async def call(self, project: Project, tool: ToolManifest, arguments: dict[str, Any]) -> dict[str, Any]:
        operation = Operation(
            operation_id=tool.operation_id, tool_name=tool.name, method=tool.method,
            path=tool.path, description=tool.description, input_schema=tool.input_schema,
        )
        return await self.call_operation(project, operation, arguments)

    async def call_operation(self, project: Project, operation: Operation, arguments: dict[str, Any]) -> dict[str, Any]:
        path = operation.path
        query: dict[str, Any] = {}
        headers: dict[str, str] = {"Accept": "application/json"}
        body: Any = None
        for name, value in arguments.items():
            location = operation.input_schema.get("properties", {}).get(name, {}).get("x-location")
            if location == "path":
                path = path.replace("{" + name + "}", quote(str(value), safe=""))
            elif location == "header":
                headers[name] = str(value)
            elif location == "body":
                body = value
            else:
                query[name] = value
        secret = self.secrets.get(project.project_id)
        if secret:
            if project.auth_type == "bearer":
                headers[project.api_key_header] = f"Bearer {secret}"
            elif project.auth_type == "api_key":
                headers[project.api_key_header] = secret
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False, transport=self.transport) as client:
                async with client.stream(operation.method, f"{project.base_url}{path}", params=query, headers=headers, json=body) as response:
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > self.max_response_bytes:
                            return {"ok": False, "status_code": response.status_code, "error": "The upstream response exceeded the configured size limit."}
                    status_code = response.status_code
                    response_headers = response.headers
        except httpx.HTTPError as error:
            return {
                "ok": False, "status_code": None,
                "error": "The upstream API did not return a definite response.",
                "outcome_unknown": operation.method not in {"GET", "HEAD"},
                "detail": type(error).__name__,
            }
        content_type = response_headers.get("content-type", "")
        text = bytes(content).decode("utf-8", errors="replace")
        body: Any
        if "json" in content_type:
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                body = text
        else:
            body = text
        if status_code >= 400:
            retry_after = response_headers.get("retry-after") if status_code == 429 else None
            return {"ok": False, "status_code": status_code, "error": body, "retry_after": retry_after}
        return {"ok": True, "status_code": status_code, "data": body}
