from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx


BASE_URL = "http://127.0.0.1:8001"
DEMO_API_URL = os.environ.get("PRODUCT_TO_MCP_DEMO_API_URL", "http://127.0.0.1:9000")
OPENAPI_PATH = Path("examples/demo-openapi.yaml")
OUTPUT_DIR = Path(".runtime/evidence")


def main() -> None:
    with httpx.Client(timeout=20) as client:
        health = client.get(f"{BASE_URL}/healthz")
        health.raise_for_status()

        project = client.post(
            f"{BASE_URL}/v1/projects",
            json={
                "name": "Evidence CRUD Demo",
                "base_url": DEMO_API_URL,
                "auth_type": "none",
            },
        )
        project.raise_for_status()
        project_id = project.json()["project_id"]

        with OPENAPI_PATH.open("rb") as source:
            upload = client.post(
                f"{BASE_URL}/v1/projects/{project_id}/openapi",
                files={"file": ("demo-openapi.yaml", source, "application/yaml")},
            )
        upload.raise_for_status()
        operations = upload.json()["operations"]
        supported = [item for item in operations if item["supported"]]
        selected_ids = [item["operation_id"] for item in supported]

        selection = client.put(
            f"{BASE_URL}/v1/projects/{project_id}/operations",
            json={"operation_ids": selected_ids},
        )
        selection.raise_for_status()

        release = client.post(f"{BASE_URL}/v1/projects/{project_id}/releases")
        release.raise_for_status()
        release_body = release.json()

        product_id = f"p-evidence-{int(time.time())}"
        create_result = client.post(
            f"{BASE_URL}/v1/releases/{release_body['release_id']}/test",
            json={
                "tool_name": "createproduct",
                "arguments": {
                    "body": {
                        "id": product_id,
                        "name": "Evidence plan",
                        "price": 99,
                    }
                },
            },
        )
        create_result.raise_for_status()

        get_result = client.post(
            f"{BASE_URL}/v1/releases/{release_body['release_id']}/test",
            json={"tool_name": "getproduct", "arguments": {"product_id": product_id}},
        )
        get_result.raise_for_status()

        replace_result = client.post(
            f"{BASE_URL}/v1/releases/{release_body['release_id']}/test",
            json={
                "tool_name": "replaceproduct",
                "arguments": {
                    "product_id": product_id,
                    "body": {
                        "id": product_id,
                        "name": "Replaced evidence plan",
                        "price": 129,
                    },
                },
            },
        )
        replace_result.raise_for_status()

        update_result = client.post(
            f"{BASE_URL}/v1/releases/{release_body['release_id']}/test",
            json={
                "tool_name": "updateproduct",
                "arguments": {
                    "product_id": product_id,
                    "body": {"price": 149},
                },
            },
        )
        update_result.raise_for_status()

        list_result = client.post(
            f"{BASE_URL}/v1/releases/{release_body['release_id']}/test",
            json={"tool_name": "listproducts", "arguments": {"limit": 20}},
        )
        list_result.raise_for_status()

        delete_result = client.post(
            f"{BASE_URL}/v1/releases/{release_body['release_id']}/test",
            json={"tool_name": "deleteproduct", "arguments": {"product_id": product_id}},
        )
        delete_result.raise_for_status()

        mcp_tools = client.post(
            f"{BASE_URL}/mcp/{release_body['deployment_slug']}/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        mcp_tools.raise_for_status()

    evidence = {
        "health": health.json(),
        "project_id": project_id,
        "discovered_tools": [
            {
                "tool_name": item["tool_name"],
                "method": item["method"],
                "supported": item["supported"],
                "reason": item["reason"],
            }
            for item in operations
        ],
        "selected_operation_ids": selected_ids,
        "release_id": release_body["release_id"],
        "deployment_slug": release_body["deployment_slug"],
        "mcp_url": f"{BASE_URL}/mcp/{release_body['deployment_slug']}/mcp",
        "created_product_result": create_result.json()["result"],
        "get_product_result": get_result.json()["result"],
        "replace_product_result": replace_result.json()["result"],
        "update_product_result": update_result.json()["result"],
        "list_after_create_result": list_result.json()["result"],
        "delete_product_result": delete_result.json()["result"],
        "mcp_tools_result": mcp_tools.json()["result"],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "backend-crud-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
