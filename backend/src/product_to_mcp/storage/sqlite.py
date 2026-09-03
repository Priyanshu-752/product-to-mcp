from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from product_to_mcp.domain.models import Operation, Project, Release, ToolManifest, now


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    auth_type TEXT NOT NULL,
                    api_key_header TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sources (
                    project_id TEXT PRIMARY KEY,
                    source_json TEXT NOT NULL,
                    operations_json TEXT NOT NULL,
                    selected_json TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                CREATE TABLE IF NOT EXISTS releases (
                    release_id TEXT PRIMARY KEY,
                    deployment_slug TEXT UNIQUE NOT NULL,
                    project_id TEXT NOT NULL,
                    manifest_hash TEXT NOT NULL,
                    tools_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                """
            )

    def create_project(self, name: str, base_url: str, auth_type: str, api_key_header: str) -> Project:
        project = Project(
            project_id=secrets.token_urlsafe(9),
            name=name.strip(),
            base_url=base_url.rstrip("/"),
            auth_type=auth_type,
            api_key_header=api_key_header.strip() or "Authorization",
            created_at=now(),
        )
        with self._connect() as db:
            db.execute(
                "INSERT INTO projects VALUES (?,?,?,?,?,?)",
                (project.project_id, project.name, project.base_url, project.auth_type,
                 project.api_key_header, project.created_at.isoformat()),
            )
        return project

    def list_projects(self) -> tuple[Project, ...]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return tuple(self._project(row) for row in rows)

    def project(self, project_id: str) -> Project:
        with self._connect() as db:
            row = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError("project_not_found")
        return self._project(row)

    def save_source(self, project_id: str, source: dict[str, Any], operations: tuple[Operation, ...], selected: tuple[str, ...] = ()) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO sources(project_id,source_json,operations_json,selected_json) VALUES(?,?,?,?) "
                "ON CONFLICT(project_id) DO UPDATE SET source_json=excluded.source_json, operations_json=excluded.operations_json, selected_json=excluded.selected_json",
                (project_id, json.dumps(source), json.dumps([item.model_dump(mode="json") for item in operations]), json.dumps(list(selected))),
            )

    def source(self, project_id: str) -> tuple[dict[str, Any], tuple[Operation, ...], tuple[str, ...]]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sources WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError("source_not_found")
        return json.loads(row["source_json"]), tuple(Operation.model_validate(item) for item in json.loads(row["operations_json"])), tuple(json.loads(row["selected_json"]))

    def select_operations(self, project_id: str, selected: tuple[str, ...]) -> tuple[Operation, ...]:
        source, operations, _ = self.source(project_id)
        known = {operation.operation_id for operation in operations if operation.supported}
        if any(item not in known for item in selected):
            raise ValueError("selected_operation_not_supported")
        self.save_source(project_id, source, operations, selected)
        return tuple(operation for operation in operations if operation.operation_id in selected)

    def create_release(self, project_id: str, tools: tuple[ToolManifest, ...]) -> Release:
        serialized = [tool.model_dump(mode="json") for tool in tools]
        manifest_hash = hashlib.sha256(json.dumps(serialized, sort_keys=True).encode()).hexdigest()
        release = Release(
            release_id=secrets.token_urlsafe(9), deployment_slug=secrets.token_urlsafe(12),
            project_id=project_id, manifest_hash=manifest_hash, tools=tools, created_at=now(),
        )
        with self._connect() as db:
            db.execute("INSERT INTO releases VALUES (?,?,?,?,?,?)", (release.release_id, release.deployment_slug, project_id, manifest_hash, json.dumps(serialized), release.created_at.isoformat()))
        return release

    def release(self, release_id: str | None = None, deployment_slug: str | None = None) -> Release:
        query = "SELECT * FROM releases WHERE release_id=?" if release_id else "SELECT * FROM releases WHERE deployment_slug=?"
        value = release_id or deployment_slug
        with self._connect() as db:
            row = db.execute(query, (value,)).fetchone()
        if row is None:
            raise KeyError("release_not_found")
        return Release(
            release_id=row["release_id"], deployment_slug=row["deployment_slug"], project_id=row["project_id"],
            manifest_hash=row["manifest_hash"], tools=tuple(ToolManifest.model_validate(item) for item in json.loads(row["tools_json"])),
            created_at=row["created_at"],
        )

    @staticmethod
    def _project(row: sqlite3.Row) -> Project:
        return Project(project_id=row["project_id"], name=row["name"], base_url=row["base_url"], auth_type=row["auth_type"], api_key_header=row["api_key_header"], created_at=row["created_at"])

