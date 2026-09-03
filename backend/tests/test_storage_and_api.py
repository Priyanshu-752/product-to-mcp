from fastapi.testclient import TestClient

from product_to_mcp.main import create_app


def test_project_upload_and_release_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PRODUCT_TO_MCP_DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite3'}")
    app = create_app()
    with TestClient(app) as client:
        project = client.post("/v1/projects", json={"name": "Demo", "base_url": "http://127.0.0.1:9000"})
        assert project.status_code == 200
        project_id = project.json()["project_id"]
        upload = client.post(
            f"/v1/projects/{project_id}/openapi",
            files={"file": ("demo.yaml", b"openapi: 3.0.3\ninfo: {title: Demo, version: '1'}\npaths:\n  /items:\n    get:\n      operationId: listItems\n      responses: {'200': {description: ok}}\n", "application/yaml")},
        )
        assert upload.status_code == 200
        assert upload.json()["operations"][0]["tool_name"] == "listitems"
        selection = client.put(f"/v1/projects/{project_id}/operations", json={"operation_ids": ["listItems"]})
        assert selection.status_code == 200
        release = client.post(f"/v1/projects/{project_id}/releases")
        assert release.status_code == 200
        assert release.json()["tools"][0]["name"] == "listitems"
        mcp = client.post(
            f"/mcp/{release.json()['deployment_slug']}/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert mcp.status_code == 200
        assert mcp.json()["result"]["tools"][0]["name"] == "listitems"
