from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from product_to_mcp.api.routes import create_router
from product_to_mcp.config import Settings
from product_to_mcp.gateway.server import MCPGateway
from product_to_mcp.storage.secrets import DatabaseSecretStore, PrototypeSecretStore
from product_to_mcp.storage.sqlite import SQLiteStore


def create_store(settings: Settings):
    if settings.database_backend == "sqlite":
        return SQLiteStore(settings.database_path)
    if settings.database_backend == "postgres":
        from product_to_mcp.storage.postgres import PostgresStore

        return PostgresStore(settings.database_url)
    raise RuntimeError("Unsupported PRODUCT_TO_MCP_DATABASE_URL. Use sqlite:/// or postgresql://.")


def create_app() -> FastAPI:
    settings = Settings.from_env()
    store = create_store(settings)
    secrets = (
        DatabaseSecretStore(store, settings.secret_encryption_key)
        if settings.secret_encryption_key
        else PrototypeSecretStore()
    )
    gateway = MCPGateway(store, secrets)
    app = FastAPI(title="Product-to-MCP Prototype", version="0.1.0")

    if settings.allowed_hosts != ("*",):
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.store = store
    app.state.secrets = secrets
    app.state.gateway = gateway
    app.include_router(create_router())

    def mcp_auth_error(request_id: object | None = None) -> JSONResponse:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32001, "message": "MCP bearer token is required."},
            },
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    async def authorize_mcp_request(request: Request) -> Response | None:
        token = settings.mcp_bearer_token
        if token is None:
            return None
        expected = f"Bearer {token}"
        if request.headers.get("authorization") == expected:
            return None
        request_id = None
        if request.method == "POST":
            try:
                body = await request.json()
                if isinstance(body, dict):
                    request_id = body.get("id")
            except Exception:
                request_id = None
        return mcp_auth_error(request_id)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "environment": settings.app_env}

    @app.get("/readyz")
    async def readyz() -> dict[str, str]:
        try:
            store.health_check()
        except Exception as error:
            raise HTTPException(status_code=503, detail="Storage is not ready.") from error
        return {
            "status": "ready",
            "database": "ok",
            "database_backend": settings.database_backend,
            "public_base_url": settings.public_base_url,
            "public_base_url_https": str(settings.public_base_url_is_https).lower(),
            "mcp_auth_configured": str(settings.mcp_bearer_token is not None).lower(),
            "persistent_secrets": str(settings.secret_encryption_key is not None).lower(),
        }

    @app.post("/mcp/{deployment_slug}/mcp")
    async def mcp_post(deployment_slug: str, request: Request):
        auth_error = await authorize_mcp_request(request)
        if auth_error is not None:
            return auth_error
        return await gateway.handle_post(deployment_slug, request)

    @app.get("/mcp/{deployment_slug}/mcp")
    async def mcp_get(deployment_slug: str, request: Request):
        auth_error = await authorize_mcp_request(request)
        if auth_error is not None:
            return auth_error
        return await gateway.handle_get(deployment_slug)

    return app


app = create_app()
