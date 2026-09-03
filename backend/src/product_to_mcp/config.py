from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


def env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw is None:
        return default
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    return values or default


class Settings(BaseModel):
    app_env: str = "development"
    database_url: str = "sqlite:///./.runtime/product-to-mcp.sqlite3"
    database_path: Path = Field(default=Path(".runtime/product-to-mcp.sqlite3"))
    public_base_url: str = "http://127.0.0.1:8000"
    smithery_api_url: str = "https://api.smithery.ai"
    max_openapi_bytes: int = 20 * 1024 * 1024
    mcp_bearer_token: str | None = None
    secret_encryption_key: str | None = None
    cors_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5175",
        "http://localhost:5175",
    )
    allowed_hosts: tuple[str, ...] = ("*",)

    @classmethod
    def from_env(cls) -> "Settings":
        raw_database = os.getenv(
            "PRODUCT_TO_MCP_DATABASE_URL", "sqlite:///./.runtime/product-to-mcp.sqlite3"
        )
        database_path = cls.model_fields["database_path"].default
        if raw_database.startswith("sqlite:///"):
            database_path = Path(raw_database[len("sqlite:///") :])
        return cls(
            app_env=os.getenv("PRODUCT_TO_MCP_ENV", cls.model_fields["app_env"].default),
            database_url=raw_database,
            database_path=database_path,
            public_base_url=os.getenv("PRODUCT_TO_MCP_PUBLIC_BASE_URL", cls.model_fields["public_base_url"].default),
            smithery_api_url=os.getenv("PRODUCT_TO_MCP_SMITHERY_API_URL", cls.model_fields["smithery_api_url"].default),
            max_openapi_bytes=int(os.getenv("PRODUCT_TO_MCP_MAX_OPENAPI_BYTES", str(20 * 1024 * 1024))),
            mcp_bearer_token=os.getenv("PRODUCT_TO_MCP_MCP_BEARER_TOKEN") or None,
            secret_encryption_key=os.getenv("PRODUCT_TO_MCP_SECRET_ENCRYPTION_KEY") or None,
            cors_origins=env_list("PRODUCT_TO_MCP_CORS_ORIGINS", cls.model_fields["cors_origins"].default),
            allowed_hosts=env_list("PRODUCT_TO_MCP_ALLOWED_HOSTS", cls.model_fields["allowed_hosts"].default),
        )

    @property
    def public_base_url_is_https(self) -> bool:
        return self.public_base_url.startswith("https://")

    @property
    def database_backend(self) -> str:
        if self.database_url.startswith("sqlite:///"):
            return "sqlite"
        if self.database_url.startswith(("postgresql://", "postgres://")):
            return "postgres"
        return "unknown"
