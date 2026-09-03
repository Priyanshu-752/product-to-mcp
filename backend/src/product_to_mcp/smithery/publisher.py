from __future__ import annotations

import json
from typing import Any

import httpx


class SmitheryPublisher:
    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    async def publish(self, *, api_key: str, qualified_name: str, mcp_url: str) -> dict[str, Any]:
        if not api_key.strip():
            raise ValueError("Smithery API key is required.")
        payload = {"mcpUrl": mcp_url, "type": "external", "url": mcp_url}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.put(
                f"{self.api_url}/servers/{qualified_name.replace('/', '%2F')}/releases",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"payload": (None, json.dumps(payload), "application/json")},
            )
        if response.status_code >= 400:
            raise ValueError(f"Smithery rejected the release ({response.status_code}).")
        return response.json()
