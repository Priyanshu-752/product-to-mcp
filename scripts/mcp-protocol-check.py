from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx


CONTROL_URL = os.environ.get("PRODUCT_TO_MCP_CONTROL_URL", "http://127.0.0.1:8001")
DEMO_API_URL = os.environ.get("PRODUCT_TO_MCP_DEMO_API_URL", "http://127.0.0.1:9001")
OPENAPI_PATH = Path("examples/demo-openapi.yaml")
OUTPUT_DIR = Path(".runtime/evidence")


def post_json(client: httpx.Client, url: str, body: dict[str, Any]) -> httpx.Response:
    return client.post(
        url,
        json=body,
        headers={
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-06-18",
        },
    )


def main() -> None:
    with httpx.Client(timeout=20) as client:
        project = client.post(
            f"{CONTROL_URL}/v1/projects",
            json={"name": "MCP Protocol Check", "base_url": DEMO_API_URL, "auth_type": "none"},
        )
        project.raise_for_status()
        project_id = project.json()["project_id"]

        with OPENAPI_PATH.open("rb") as source:
            upload = client.post(
                f"{CONTROL_URL}/v1/projects/{project_id}/openapi",
                files={"file": ("demo-openapi.yaml", source, "application/yaml")},
            )
        upload.raise_for_status()
        operations = upload.json()["operations"]
        selected_ids = [operation["operation_id"] for operation in operations if operation["supported"]]

        selection = client.put(f"{CONTROL_URL}/v1/projects/{project_id}/operations", json={"operation_ids": selected_ids})
        selection.raise_for_status()

        release = client.post(f"{CONTROL_URL}/v1/projects/{project_id}/releases")
        release.raise_for_status()
        release_body = release.json()
        endpoint = f"{CONTROL_URL}/mcp/{release_body['deployment_slug']}/mcp"

        initialize = post_json(
            client,
            endpoint,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "product-to-mcp-protocol-check", "version": "1.0.0"},
                },
            },
        )
        initialized = post_json(client, endpoint, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools_list = post_json(client, endpoint, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

        product_id = f"p-mcp-{int(time.time())}"
        tool_call = post_json(
            client,
            endpoint,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "createproduct",
                    "arguments": {"body": {"id": product_id, "name": "MCP protocol plan", "price": 177}},
                },
            },
        )
        get_stream = client.get(endpoint, headers={"Accept": "text/event-stream", "MCP-Protocol-Version": "2025-06-18"})

    result = {
        "endpoint": endpoint,
        "selected_operation_ids": selected_ids,
        "initialize": {"http_status": initialize.status_code, "body": initialize.json()},
        "initialized_notification": {"http_status": initialized.status_code, "body_length": len(initialized.content)},
        "tools_list": {"http_status": tools_list.status_code, "body": tools_list.json()},
        "tools_call_createproduct": {"http_status": tool_call.status_code, "body": tool_call.json()},
        "get_sse_probe": {
            "http_status": get_stream.status_code,
            "content_type": get_stream.headers.get("content-type"),
            "body": get_stream.text,
        },
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "mcp-protocol-check.json"
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
