from fastapi.testclient import TestClient

from product_to_mcp.main import create_app


OPENAPI = b"""
openapi: 3.0.3
info: {title: Demo, version: '1'}
paths:
  /products:
    get:
      operationId: searchProducts
      summary: Search catalog products.
      tags: [Catalog]
      parameters:
        - {name: query, in: query, description: Search text, schema: {type: string}}
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                type: object
                properties:
                  items: {type: array, items: {type: object}}
    options:
      operationId: productOptions
      responses:
        '204': {description: ok}
  /categories:
    get:
      operationId: listCategories
      summary: List product categories.
      tags: [Catalog]
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema: {type: array, items: {type: string}}
"""


def test_action_profile_release_and_mcp_tool_list(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PRODUCT_TO_MCP_DATABASE_URL", f"sqlite:///{tmp_path / 'actions.sqlite3'}")
    monkeypatch.setenv("PRODUCT_TO_MCP_ALLOW_LEGACY_RELEASES", "true")
    monkeypatch.delenv("PRODUCT_TO_MCP_MCP_BEARER_TOKEN", raising=False)
    app = create_app()
    with TestClient(app) as client:
        project = client.post("/v1/projects", json={"name": "Catalog", "base_url": "https://api.example.com"}).json()
        project_id = project["project_id"]
        upload = client.post(f"/v1/projects/{project_id}/openapi", files={"file": ("catalog.yaml", OPENAPI, "application/yaml")})
        assert upload.status_code == 200
        assert upload.json()["groups"][0]["name"] == "Catalog"
        assert upload.json()["groups"][0]["operation_ids"] == ["searchProducts", "listCategories"]
        unsupported = next(item for item in upload.json()["operations"] if item["operation_id"] == "productOptions")
        assert unsupported["supported"] is False
        regrouped = client.put(f"/v1/projects/{project_id}/groups", json={"groups": upload.json()["groups"]})
        assert regrouped.status_code == 200
        selected = client.put(f"/v1/projects/{project_id}/operations", json={"operation_ids": ["searchProducts"]})
        assert selected.status_code == 200

        workspace = client.get(f"/v1/projects/{project_id}/workspace")
        assert workspace.status_code == 200
        assert workspace.json()["limits"]["max_chain_steps"] == 10

        legacy_release = client.post(f"/v1/projects/{project_id}/releases")
        assert legacy_release.status_code == 200
        assert legacy_release.json()["tools"][0]["name"] == "search_products"
        assert legacy_release.json()["tools"][0]["output_schema"]["type"] == "object"

        created = client.post(f"/v1/projects/{project_id}/actions", json={"operation_ids": ["searchProducts"]})
        assert created.status_code == 200
        assert created.json()["name"] == "search_products_action"
        assert created.json()["title"] == "Search Products Action"
        assert created.json()["description"] == "Run GET /products: Search catalog products."
        action_id = created.json()["action_id"]
        validated = client.post(f"/v1/projects/{project_id}/actions/{action_id}/validate")
        assert validated.status_code == 200
        assert validated.json()["valid"] is True
        approved = client.post(f"/v1/projects/{project_id}/actions/{action_id}/approve")
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        profile = client.post(f"/v1/projects/{project_id}/profiles", json={"name": "Support", "description": "Tools for support agents.", "action_ids": [action_id]})
        assert profile.status_code == 200
        release = client.post(f"/v1/projects/{project_id}/releases", json={"profile_id": profile.json()["profile_id"]})
        assert release.status_code == 200
        assert [tool["kind"] for tool in release.json()["tools"]] == ["legacy", "legacy", "action"]
        assert [tool["name"] for tool in release.json()["tools"]] == ["search_products", "list_categories", "search_products_action"]
        assert release.json()["tool_mode"] == "api_and_actions"
        assert release.json()["tool_counts"] == {"api": 2, "actions": 1, "total": 3}
        assert release.json()["tools"][0]["kind"] == "legacy"
        assert release.json()["tools"][2]["kind"] == "action"
        actions_only = client.post(f"/v1/projects/{project_id}/releases", json={"profile_id": profile.json()["profile_id"], "tool_mode": "actions_only"})
        assert actions_only.status_code == 200
        assert [tool["name"] for tool in actions_only.json()["tools"]] == ["search_products_action"]
        assert actions_only.json()["tool_mode"] == "actions_only"
        api_only = client.post(f"/v1/projects/{project_id}/releases", json={"profile_id": None, "tool_mode": "api_only"})
        assert api_only.status_code == 200
        assert [tool["name"] for tool in api_only.json()["tools"]] == ["search_products", "list_categories"]
        assert api_only.json()["tool_mode"] == "api_only"
        missing_metadata = client.post(
            f"/v1/releases/{release.json()['release_id']}/smithery/publish",
            json={"namespace": "@acme", "server_name": "catalog-mcp", "smithery_api_key": "key"},
        )
        assert missing_metadata.status_code == 422
        blank_metadata = client.post(
            f"/v1/releases/{release.json()['release_id']}/smithery/publish",
            json={
                "namespace": "@acme",
                "server_name": "catalog-mcp",
                "display_name": "Catalog MCP",
                "description": " ",
                "homepage": "https://example.com",
                "icon_url": "https://example.com/icon.png",
                "smithery_api_key": "key",
            },
        )
        assert blank_metadata.status_code == 422

        listed = client.post(
            f"/mcp/{release.json()['deployment_slug']}/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        raw_tool = listed.json()["result"]["tools"][0]
        action_tool = listed.json()["result"]["tools"][2]
        assert raw_tool["name"] == "search_products"
        assert raw_tool["title"] == "Search Products"
        assert raw_tool["inputSchema"]["properties"]["query"]["description"] == "Search text"
        assert raw_tool["annotations"]["readOnlyHint"] is True
        assert "outputSchema" in raw_tool
        assert action_tool["name"] == "search_products_action"
        assert action_tool["title"] == "Search Products Action"
        assert action_tool["description"] == "Run GET /products: Search catalog products."
        assert action_tool["inputSchema"]["properties"]["query"]["description"] == "Search text"
        assert action_tool["annotations"]["readOnlyHint"] is True
        assert "outputSchema" in action_tool

        changed = OPENAPI.replace(
            b"parameters:\n        - {name: query, in: query, description: Search text, schema: {type: string}}",
            b"parameters:\n        - {name: status, in: query, required: true, description: Search status, schema: {type: string}}",
        )
        reimported = client.post(f"/v1/projects/{project_id}/openapi", files={"file": ("catalog.yaml", changed, "application/yaml")})
        assert action_id in reimported.json()["invalidated_action_ids"]
        current_action = client.get(f"/v1/projects/{project_id}/actions/{action_id}")
        assert current_action.json()["status"] == "draft"

        old_release = client.post(
            f"/mcp/{release.json()['deployment_slug']}/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert old_release.status_code == 200
        assert old_release.json()["result"]["tools"][0]["name"] == "search_products"
        assert old_release.json()["result"]["tools"][1]["name"] == "list_categories"
        assert old_release.json()["result"]["tools"][2]["name"] == "search_products_action"
