from __future__ import annotations

import json
from typing import Any

import httpx


class SmitheryPublisher:
    def __init__(self, api_url: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.api_url = api_url.rstrip("/")
        self.transport = transport

    async def publish(
        self, *, api_key: str, qualified_name: str, mcp_url: str, display_name: str,
        description: str, homepage: str, icon_url: str, repository_url: str | None = None,
        license: str | None = None, unlisted: bool = False,
    ) -> dict[str, Any]:
        if not api_key.strip():
            raise ValueError("Smithery API key is required.")
        encoded_name = qualified_name.replace("/", "%2F")
        headers = {"Authorization": f"Bearer {api_key}"}
        server_payload = {"displayName": display_name, "description": description}
        metadata_payload: dict[str, Any] = {
            **server_payload,
            "homepage": homepage,
            "iconUrl": icon_url,
            "unlisted": unlisted,
        }
        if repository_url:
            metadata_payload["repositoryUrl"] = repository_url
        if license:
            metadata_payload["license"] = license
        release_payload = {
            "mcpUrl": mcp_url,
            "type": "external",
            "url": mcp_url,
            "configSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        }
        async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
            create = await client.put(
                f"{self.api_url}/servers/{encoded_name}",
                headers={**headers, "Content-Type": "application/json"},
                json=server_payload,
            )
            if create.status_code >= 400:
                raise ValueError(f"Smithery rejected the server metadata ({create.status_code}).")
            update = await client.patch(
                f"{self.api_url}/servers/{encoded_name}",
                headers={**headers, "Content-Type": "application/json"},
                json=metadata_payload,
            )
            if update.status_code >= 400:
                raise ValueError(f"Smithery rejected the server metadata update ({update.status_code}).")
            release = await client.put(
                f"{self.api_url}/servers/{encoded_name}/releases",
                headers=headers,
                files={"payload": (None, json.dumps(release_payload), "application/json")},
            )
        if release.status_code >= 400:
            raise ValueError(f"Smithery rejected the release ({release.status_code}).")
        return release.json()
