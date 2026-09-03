from __future__ import annotations

from fastapi import FastAPI, Request

from product_to_mcp.api.routes import create_router
from product_to_mcp.config import Settings
from product_to_mcp.gateway.server import MCPGateway
from product_to_mcp.storage.secrets import PrototypeSecretStore
from product_to_mcp.storage.sqlite import SQLiteStore


def create_app() -> FastAPI:
    settings = Settings.from_env()
    store = SQLiteStore(settings.database_path)
    secrets = PrototypeSecretStore()
    gateway = MCPGateway(store, secrets)
    app = FastAPI(title="Product-to-MCP Prototype", version="0.1.0")
    app.state.settings = settings
    app.state.store = store
    app.state.secrets = secrets
    app.state.gateway = gateway
    app.include_router(create_router())

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        return {"status": "ready"}

    @app.post("/mcp/{deployment_slug}/mcp")
    async def mcp_post(deployment_slug: str, request: Request):
        return await gateway.handle_post(deployment_slug, request)

    @app.get("/mcp/{deployment_slug}/mcp")
    async def mcp_get(deployment_slug: str):
        return await gateway.handle_get(deployment_slug)

    return app


app = create_app()

