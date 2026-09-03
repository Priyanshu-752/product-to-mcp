from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from product_to_mcp.domain.models import Project, ToolManifest
from product_to_mcp.storage.secrets import PrototypeSecretStore


class UpstreamExecutor:
    def __init__(self, secrets: PrototypeSecretStore) -> None:
        self.secrets = secrets

    async def call(self, project: Project, tool: ToolManifest, arguments: dict[str, Any]) -> dict[str, Any]:
        path = tool.path
        query: dict[str, Any] = {}
        headers: dict[str, str] = {"Accept": "application/json"}
        body: Any = None
        for name, value in arguments.items():
            location = tool.input_schema.get("properties", {}).get(name, {}).get("x-location")
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
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.request(tool.method, f"{project.base_url}{path}", params=query, headers=headers, json=body)
        content_type = response.headers.get("content-type", "")
        body: Any
        if "json" in content_type:
            try:
                body = response.json()
            except ValueError:
                body = response.text
        else:
            body = response.text
        if response.status_code >= 400:
            return {"ok": False, "status_code": response.status_code, "error": body}
        return {"ok": True, "status_code": response.status_code, "data": body}
