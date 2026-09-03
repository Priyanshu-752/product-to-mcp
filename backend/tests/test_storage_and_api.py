from fastapi.testclient import TestClient

from product_to_mcp.config import Settings
from product_to_mcp.main import create_app
from product_to_mcp.storage.secrets import DatabaseSecretStore
from product_to_mcp.storage.sqlite import SQLiteStore


def test_project_upload_and_release_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("PRODUCT_TO_MCP_MCP_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("PRODUCT_TO_MCP_DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite3'}")
    app = create_app()
    with TestClient(app) as client:
        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["database"] == "ok"

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
        assert release.json()["mcp_url"].endswith(f"/mcp/{release.json()['deployment_slug']}/mcp")
        mcp = client.post(
            f"/mcp/{release.json()['deployment_slug']}/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert mcp.status_code == 200
        assert mcp.json()["result"]["tools"][0]["name"] == "listitems"


def test_mcp_endpoint_can_require_bearer_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PRODUCT_TO_MCP_DATABASE_URL", f"sqlite:///{tmp_path / 'test.sqlite3'}")
    monkeypatch.setenv("PRODUCT_TO_MCP_MCP_BEARER_TOKEN", "test-mcp-token")
    app = create_app()
    with TestClient(app) as client:
        project = client.post("/v1/projects", json={"name": "Demo", "base_url": "http://127.0.0.1:9000"})
        project_id = project.json()["project_id"]
        client.post(
            f"/v1/projects/{project_id}/openapi",
            files={"file": ("demo.yaml", b"openapi: 3.0.3\ninfo: {title: Demo, version: '1'}\npaths:\n  /items:\n    get:\n      operationId: listItems\n      responses: {'200': {description: ok}}\n", "application/yaml")},
        )
        client.put(f"/v1/projects/{project_id}/operations", json={"operation_ids": ["listItems"]})
        release = client.post(f"/v1/projects/{project_id}/releases").json()
        payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

        blocked = client.post(f"/mcp/{release['deployment_slug']}/mcp", json=payload)
        assert blocked.status_code == 401

        allowed = client.post(
            f"/mcp/{release['deployment_slug']}/mcp",
            json=payload,
            headers={"Authorization": "Bearer test-mcp-token"},
        )
        assert allowed.status_code == 200


def test_settings_accept_postgres_database_url(monkeypatch) -> None:
    monkeypatch.setenv("PRODUCT_TO_MCP_DATABASE_URL", "postgresql://user:password@db.example.com/app")

    settings = Settings.from_env()

    assert settings.database_backend == "postgres"
    assert settings.database_url == "postgresql://user:password@db.example.com/app"


def test_database_secret_store_persists_encrypted_values(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "test.sqlite3")
    project = store.create_project("Demo", "http://127.0.0.1:9000", "bearer", "Authorization")
    secrets = DatabaseSecretStore(store, "local-test-encryption-key")

    secrets.put(project.project_id, "upstream-secret")

    assert secrets.get(project.project_id) == "upstream-secret"
    assert store.get_secret(project.project_id) != "upstream-secret"
