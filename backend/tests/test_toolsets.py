from fastapi.testclient import TestClient

from product_to_mcp.main import create_app
from product_to_mcp.openapi.toolsets import derived_toolsets, resolve_toolset_operations
from product_to_mcp.domain.models import Operation


def test_derived_toolsets_are_stable_and_exclude_unsupported() -> None:
    def operation(operation_id: str, group: str, supported: bool = True) -> Operation:
        return Operation(
            operation_id=operation_id, tool_name=operation_id, method="GET", path=f"/{operation_id}",
            description=operation_id, input_schema={"type": "object"}, default_group=group, supported=supported,
        )

    operations = (operation("one", "Orders"), operation("two", " orders "), operation("three", "Billing"), operation("four", "Billing", False))
    toolsets = derived_toolsets(operations)
    assert len(toolsets) == 2
    assert toolsets[0]["operation_ids"] == ["one", "two"]
    assert toolsets[0]["read_count"] == 2
    assert toolsets[1]["operation_ids"] == ["three"]
    assert derived_toolsets(tuple(reversed(operations)))[-1]["toolset_id"] == toolsets[0]["toolset_id"]
    assert resolve_toolset_operations(operations, (toolsets[1]["toolset_id"],)) == ("three",)


OPENAPI = b"""
openapi: 3.1.0
info: {title: Toolset Demo, version: '1'}
paths:
  /products:
    get:
      operationId: listProducts
      tags: [Products]
      summary: List products.
      responses:
        '200': {description: OK, content: {application/json: {schema: {type: object}}}}
  /orders:
    get:
      operationId: listOrders
      tags: [Orders]
      summary: List orders.
      responses:
        '200': {description: OK, content: {application/json: {schema: {type: object}}}}
  /billing:
    get:
      operationId: listBills
      tags: [Billing]
      summary: List bills.
      responses:
        '200': {description: OK, content: {application/json: {schema: {type: object}}}}
"""


def test_release_toolsets_filter_mcp_tools_and_keep_actions_independent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PRODUCT_TO_MCP_DATABASE_URL", f"sqlite:///{tmp_path / 'toolsets.sqlite3'}")
    monkeypatch.delenv("PRODUCT_TO_MCP_MCP_BEARER_TOKEN", raising=False)
    with TestClient(create_app()) as client:
        project = client.post("/v1/projects", json={"name": "Toolsets", "base_url": "https://api.example.com"}).json()
        project_id = project["project_id"]
        uploaded = client.post(f"/v1/projects/{project_id}/openapi", files={"file": ("api.yaml", OPENAPI, "application/yaml")})
        assert uploaded.status_code == 200
        toolsets = {item["name"]: item["toolset_id"] for item in uploaded.json()["toolsets"]}
        assert set(toolsets) == {"Products", "Orders", "Billing"}
        assert client.get(f"/v1/projects/{project_id}/workspace").json()["toolsets"] == uploaded.json()["toolsets"]

        action = client.post(f"/v1/projects/{project_id}/actions", json={"operation_ids": ["listOrders"]}).json()
        action_id = action["action_id"]
        assert client.post(f"/v1/projects/{project_id}/actions/{action_id}/validate").json()["valid"] is True
        assert client.post(f"/v1/projects/{project_id}/actions/{action_id}/approve").status_code == 200
        profile = client.post(f"/v1/projects/{project_id}/profiles", json={"name": "Orders", "description": "Order actions", "action_ids": [action_id]}).json()

        body = {"tool_mode": "api_and_actions", "profile_id": profile["profile_id"], "selected_toolset_ids": [toolsets["Products"]]}
        preview = client.post(f"/v1/projects/{project_id}/releases/preview", json=body)
        assert preview.status_code == 200
        assert preview.json()["tool_counts"] == {"api": 1, "actions": 1, "total": 2}
        release = client.post(f"/v1/projects/{project_id}/releases", json=body)
        assert release.status_code == 200
        assert [item["name"] for item in release.json()["tools"]] == preview.json()["tool_names"]
        assert [item["name"] for item in release.json()["tools"]] == ["list_products", "list_orders_action"]

        mcp_url = f"/mcp/{release.json()['deployment_slug']}/mcp"
        listed = client.post(mcp_url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()["result"]["tools"]
        assert [item["name"] for item in listed] == ["list_products", "list_orders_action"]
        excluded = client.post(mcp_url, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_bills", "arguments": {}}})
        assert excluded.status_code == 400
        assert excluded.json()["error"]["message"] == "Tool is not enabled in this release."

        api_only = client.post(f"/v1/projects/{project_id}/releases", json={"tool_mode": "api_only", "selected_toolset_ids": [toolsets["Billing"]]})
        assert [item["name"] for item in api_only.json()["tools"]] == ["list_bills"]
        actions_only = client.post(f"/v1/projects/{project_id}/releases", json={"tool_mode": "actions_only", "profile_id": profile["profile_id"], "selected_toolset_ids": []})
        assert [item["name"] for item in actions_only.json()["tools"]] == ["list_orders_action"]
        legacy = client.post(f"/v1/projects/{project_id}/releases", json={"tool_mode": "api_only"})
        assert legacy.json()["tool_counts"]["api"] == 3

        for invalid in (
            {"tool_mode": "api_only", "selected_toolset_ids": []},
            {"tool_mode": "api_only", "selected_toolset_ids": ["ts_unknown"]},
            {"tool_mode": "api_only", "selected_toolset_ids": [toolsets["Products"], toolsets["Products"]]},
            {"tool_mode": "actions_only", "profile_id": profile["profile_id"], "selected_toolset_ids": [toolsets["Products"]]},
        ):
            assert client.post(f"/v1/projects/{project_id}/releases", json=invalid).status_code == 400

        changed = OPENAPI.replace(b"tags: [Products]", b"tags: [Catalog]")
        assert client.post(f"/v1/projects/{project_id}/openapi", files={"file": ("api.yaml", changed, "application/yaml")}).status_code == 200
        stale = client.post(f"/v1/projects/{project_id}/releases", json={"tool_mode": "api_only", "selected_toolset_ids": [toolsets["Products"]]})
        assert stale.status_code == 400
        old_list = client.post(mcp_url, json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"}).json()["result"]["tools"]
        assert [item["name"] for item in old_list] == ["list_products", "list_orders_action"]


def test_custom_toolsets_persist_filter_release_and_require_review_after_import(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PRODUCT_TO_MCP_DATABASE_URL", f"sqlite:///{tmp_path / 'custom.sqlite3'}")
    with TestClient(create_app()) as client:
        project_id = client.post("/v1/projects", json={"name": "Custom", "base_url": "https://api.example.com"}).json()["project_id"]
        base = f"/v1/projects/{project_id}"
        assert client.post(f"{base}/openapi", files={"file": ("api.yaml", OPENAPI, "application/yaml")}).status_code == 200
        invalid = client.post(f"{base}/custom-toolsets", json={"name": "Bad", "operation_ids": ["unknown"]})
        assert invalid.status_code == 400
        created = client.post(f"{base}/custom-toolsets", json={"name": "Support", "operation_ids": ["listProducts", "listOrders"]})
        assert created.status_code == 200
        custom_id = created.json()["toolset_id"]
        assert created.json()["custom"] is True
        assert len(client.get(f"{base}/workspace").json()["toolsets"]) == 4
        duplicate_name = client.post(f"{base}/custom-toolsets", json={"name": "support", "operation_ids": ["listOrders"]})
        assert duplicate_name.status_code == 400
        toolsets = client.get(f"{base}/workspace").json()["toolsets"]
        products_id = next(item["toolset_id"] for item in toolsets if item["name"] == "Products")
        body = {"tool_mode": "api_only", "selected_toolset_ids": [custom_id, products_id]}
        preview = client.post(f"{base}/releases/preview", json=body)
        release = client.post(f"{base}/releases", json=body)
        assert preview.json()["tool_counts"]["api"] == 2
        assert [item["name"] for item in release.json()["tools"]] == ["list_products", "list_orders"]
        changed = OPENAPI.replace(b"operationId: listOrders", b"operationId: listNewOrders")
        assert client.post(f"{base}/openapi", files={"file": ("api.yaml", changed, "application/yaml")}).status_code == 200
        custom = next(item for item in client.get(f"{base}/workspace").json()["toolsets"] if item["toolset_id"] == custom_id)
        assert custom["needs_review"] is True
        assert client.post(f"{base}/releases", json=body).status_code == 400
        updated = client.put(f"{base}/custom-toolsets/{custom_id}", json={"name": "Support", "operation_ids": ["listProducts", "listNewOrders"]})
        assert updated.status_code == 200
        assert updated.json()["needs_review"] is False
        assert client.delete(f"{base}/custom-toolsets/{custom_id}").status_code == 204
        assert client.post(f"{base}/releases", json={"tool_mode": "api_only", "selected_toolset_ids": [custom_id]}).status_code == 400
        old = client.get(f"/v1/releases/{release.json()['release_id']}").json()
        assert [item["name"] for item in old["tools"]] == ["list_products", "list_orders"]
