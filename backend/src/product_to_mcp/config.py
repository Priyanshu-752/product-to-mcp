from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field


class Settings(BaseModel):
    database_path: Path = Field(default=Path(".runtime/product-to-mcp.sqlite3"))
    public_base_url: str = "http://127.0.0.1:8000"
    smithery_api_url: str = "https://api.smithery.ai"
    max_openapi_bytes: int = 20 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        raw_database = os.getenv(
            "PRODUCT_TO_MCP_DATABASE_URL", "sqlite:///./.runtime/product-to-mcp.sqlite3"
        )
        if raw_database.startswith("sqlite:///"):
            raw_database = raw_database[len("sqlite:///") :]
        return cls(
            database_path=Path(raw_database),
            public_base_url=os.getenv("PRODUCT_TO_MCP_PUBLIC_BASE_URL", cls.model_fields["public_base_url"].default),
            smithery_api_url=os.getenv("PRODUCT_TO_MCP_SMITHERY_API_URL", cls.model_fields["smithery_api_url"].default),
            max_openapi_bytes=int(os.getenv("PRODUCT_TO_MCP_MAX_OPENAPI_BYTES", str(20 * 1024 * 1024))),
        )

