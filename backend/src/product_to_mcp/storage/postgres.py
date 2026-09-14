from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from product_to_mcp.domain.models import (
    ActionDefinition, ActionToolManifest, Operation, OperationGroup, Project,
    Release, ToolManifest, ToolProfile, now,
)


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        from psycopg.rows import dict_row

        self.database_url = self._normalize_database_url(database_url)
        self.row_factory = dict_row
        self._initialize()

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url, autocommit=True, row_factory=self.row_factory)

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute(
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
                CREATE TABLE IF NOT EXISTS upstream_secrets (
                    project_id TEXT PRIMARY KEY,
                    encrypted_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS operation_groups (
                    group_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    sort_order INTEGER NOT NULL,
                    hidden BOOLEAN NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, name),
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                CREATE TABLE IF NOT EXISTS operation_group_members (
                    project_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    group_id TEXT NOT NULL,
                    sort_order INTEGER NOT NULL,
                    PRIMARY KEY(project_id, operation_id),
                    FOREIGN KEY(group_id) REFERENCES operation_groups(group_id)
                );
                CREATE TABLE IF NOT EXISTS actions (
                    action_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, name),
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                CREATE TABLE IF NOT EXISTS tool_profiles (
                    profile_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_id, name),
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                CREATE TABLE IF NOT EXISTS custom_toolsets (
                    toolset_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    operation_ids_json TEXT NOT NULL,
                    UNIQUE(project_id, name),
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
                """
            )
            db.execute("ALTER TABLE releases ADD COLUMN IF NOT EXISTS profile_id TEXT")
            db.execute("INSERT INTO schema_migrations(version,applied_at) VALUES(1,%s) ON CONFLICT(version) DO NOTHING", (now().isoformat(),))

    def health_check(self) -> None:
        with self._connect() as db:
            db.execute("SELECT 1").fetchone()
            db.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name='projects'"
            ).fetchone()

    def list_custom_toolsets(self, project_id: str) -> tuple[dict[str, Any], ...]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM custom_toolsets WHERE project_id=%s ORDER BY name", (project_id,)).fetchall()
        return tuple({"toolset_id": row["toolset_id"], "name": row["name"], "operation_ids": json.loads(row["operation_ids_json"])} for row in rows)

    def save_custom_toolset(self, project_id: str, toolset_id: str, name: str, operation_ids: tuple[str, ...]) -> None:
        with self._connect() as db:
            db.execute("INSERT INTO custom_toolsets(toolset_id,project_id,name,operation_ids_json) VALUES(%s,%s,%s,%s) "
                       "ON CONFLICT(toolset_id) DO UPDATE SET name=excluded.name,operation_ids_json=excluded.operation_ids_json",
                       (toolset_id, project_id, name, json.dumps(operation_ids)))

    def delete_custom_toolset(self, project_id: str, toolset_id: str) -> None:
        with self._connect() as db:
            cursor = db.execute("DELETE FROM custom_toolsets WHERE project_id=%s AND toolset_id=%s", (project_id, toolset_id))
            if not cursor.rowcount:
                raise KeyError(toolset_id)

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
                "INSERT INTO projects VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    project.project_id,
                    project.name,
                    project.base_url,
                    project.auth_type,
                    project.api_key_header,
                    project.created_at.isoformat(),
                ),
            )
        return project

    def list_projects(self) -> tuple[Project, ...]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return tuple(self._project(row) for row in rows)

    def project(self, project_id: str) -> Project:
        with self._connect() as db:
            row = db.execute("SELECT * FROM projects WHERE project_id=%s", (project_id,)).fetchone()
        if row is None:
            raise KeyError("project_not_found")
        return self._project(row)

    def save_source(
        self,
        project_id: str,
        source: dict[str, Any],
        operations: tuple[Operation, ...],
        selected: tuple[str, ...] = (),
    ) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO sources(project_id,source_json,operations_json,selected_json) VALUES(%s,%s,%s,%s) "
                "ON CONFLICT(project_id) DO UPDATE SET source_json=excluded.source_json, operations_json=excluded.operations_json, selected_json=excluded.selected_json",
                (
                    project_id,
                    json.dumps(source),
                    json.dumps([item.model_dump(mode="json") for item in operations]),
                    json.dumps(list(selected)),
                ),
            )

    def sync_groups(self, project_id: str, operations: tuple[Operation, ...]) -> tuple[OperationGroup, ...]:
        with self._connect() as db:
            memberships = {row["operation_id"]: row["group_id"] for row in db.execute("SELECT operation_id,group_id FROM operation_group_members WHERE project_id=%s", (project_id,)).fetchall()}
            groups = {row["name"].casefold(): row["group_id"] for row in db.execute("SELECT group_id,name FROM operation_groups WHERE project_id=%s", (project_id,)).fetchall()}
            current_ids = {item.operation_id for item in operations if item.supported}
            for operation_id in set(memberships) - current_ids:
                db.execute("DELETE FROM operation_group_members WHERE project_id=%s AND operation_id=%s", (project_id, operation_id))
            for order, operation in enumerate(operations):
                if not operation.supported:
                    continue
                if operation.operation_id in memberships:
                    continue
                group_name = operation.default_group or "General"
                group_id = groups.get(group_name.casefold())
                if group_id is None:
                    group_id = f"grp_{secrets.token_urlsafe(8)}"
                    stamp = now().isoformat()
                    db.execute("INSERT INTO operation_groups VALUES(%s,%s,%s,%s,%s,%s,%s)", (group_id, project_id, group_name, len(groups), False, stamp, stamp))
                    groups[group_name.casefold()] = group_id
                db.execute("INSERT INTO operation_group_members VALUES(%s,%s,%s,%s)", (project_id, operation.operation_id, group_id, order))
        return self.list_groups(project_id)

    def list_groups(self, project_id: str) -> tuple[OperationGroup, ...]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM operation_groups WHERE project_id=%s ORDER BY sort_order,name", (project_id,)).fetchall()
            members = db.execute("SELECT group_id,operation_id FROM operation_group_members WHERE project_id=%s ORDER BY sort_order", (project_id,)).fetchall()
        by_group: dict[str, list[str]] = {}
        for row in members:
            by_group.setdefault(row["group_id"], []).append(row["operation_id"])
        return tuple(OperationGroup(
            group_id=row["group_id"], project_id=row["project_id"], name=row["name"],
            sort_order=row["sort_order"], hidden=bool(row["hidden"]),
            operation_ids=tuple(by_group.get(row["group_id"], [])), created_at=row["created_at"], updated_at=row["updated_at"],
        ) for row in rows)

    def replace_groups(self, project_id: str, groups: tuple[OperationGroup, ...]) -> tuple[OperationGroup, ...]:
        with self._connect() as db:
            db.execute("DELETE FROM operation_group_members WHERE project_id=%s", (project_id,))
            incoming = [item.group_id for item in groups]
            for item in groups:
                db.execute(
                    "INSERT INTO operation_groups(group_id,project_id,name,sort_order,hidden,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT(group_id) DO UPDATE SET name=excluded.name,sort_order=excluded.sort_order,hidden=excluded.hidden,updated_at=excluded.updated_at",
                    (item.group_id, project_id, item.name, item.sort_order, item.hidden, item.created_at.isoformat(), now().isoformat()),
                )
                for order, operation_id in enumerate(item.operation_ids):
                    db.execute("INSERT INTO operation_group_members VALUES(%s,%s,%s,%s)", (project_id, operation_id, item.group_id, order))
            if incoming:
                db.execute("DELETE FROM operation_groups WHERE project_id=%s AND NOT (group_id = ANY(%s))", (project_id, incoming))
            else:
                db.execute("DELETE FROM operation_groups WHERE project_id=%s", (project_id,))
        return self.list_groups(project_id)

    def list_actions(self, project_id: str) -> tuple[ActionDefinition, ...]:
        with self._connect() as db:
            rows = db.execute("SELECT spec_json FROM actions WHERE project_id=%s ORDER BY created_at", (project_id,)).fetchall()
        return tuple(ActionDefinition.model_validate(json.loads(row["spec_json"])) for row in rows)

    def action(self, action_id: str) -> ActionDefinition:
        with self._connect() as db:
            row = db.execute("SELECT spec_json FROM actions WHERE action_id=%s", (action_id,)).fetchone()
        if row is None:
            raise KeyError("action_not_found")
        return ActionDefinition.model_validate(json.loads(row["spec_json"]))

    def save_action(self, action: ActionDefinition) -> ActionDefinition:
        with self._connect() as db:
            db.execute(
                "INSERT INTO actions(action_id,project_id,name,spec_json,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(action_id) DO UPDATE SET name=excluded.name,spec_json=excluded.spec_json,updated_at=excluded.updated_at",
                (action.action_id, action.project_id, action.name, action.model_dump_json(by_alias=True), action.created_at.isoformat(), action.updated_at.isoformat()),
            )
        return action

    def delete_action(self, action_id: str) -> None:
        with self._connect() as db:
            if db.execute("DELETE FROM actions WHERE action_id=%s", (action_id,)).rowcount == 0:
                raise KeyError("action_not_found")

    def invalidate_actions(self, project_id: str, operation_ids: set[str]) -> tuple[str, ...]:
        invalidated: list[str] = []
        for action in self.list_actions(project_id):
            if action.status != "draft" and any(step.operation_id in operation_ids for step in action.steps):
                self.save_action(action.model_copy(update={"status": "draft", "updated_at": now()}))
                invalidated.append(action.action_id)
        return tuple(invalidated)

    def list_profiles(self, project_id: str) -> tuple[ToolProfile, ...]:
        with self._connect() as db:
            rows = db.execute("SELECT spec_json FROM tool_profiles WHERE project_id=%s ORDER BY created_at", (project_id,)).fetchall()
        return tuple(ToolProfile.model_validate(json.loads(row["spec_json"])) for row in rows)

    def profile(self, profile_id: str) -> ToolProfile:
        with self._connect() as db:
            row = db.execute("SELECT spec_json FROM tool_profiles WHERE profile_id=%s", (profile_id,)).fetchone()
        if row is None:
            raise KeyError("profile_not_found")
        return ToolProfile.model_validate(json.loads(row["spec_json"]))

    def save_profile(self, profile: ToolProfile) -> ToolProfile:
        with self._connect() as db:
            db.execute(
                "INSERT INTO tool_profiles(profile_id,project_id,name,spec_json,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT(profile_id) DO UPDATE SET name=excluded.name,spec_json=excluded.spec_json,updated_at=excluded.updated_at",
                (profile.profile_id, profile.project_id, profile.name, profile.model_dump_json(), profile.created_at.isoformat(), profile.updated_at.isoformat()),
            )
        return profile

    def delete_profile(self, profile_id: str) -> None:
        with self._connect() as db:
            if db.execute("DELETE FROM tool_profiles WHERE profile_id=%s", (profile_id,)).rowcount == 0:
                raise KeyError("profile_not_found")

    def source(self, project_id: str) -> tuple[dict[str, Any], tuple[Operation, ...], tuple[str, ...]]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM sources WHERE project_id=%s", (project_id,)).fetchone()
        if row is None:
            raise KeyError("source_not_found")
        return (
            json.loads(row["source_json"]),
            tuple(Operation.model_validate(item) for item in json.loads(row["operations_json"])),
            tuple(json.loads(row["selected_json"])),
        )

    def select_operations(self, project_id: str, selected: tuple[str, ...]) -> tuple[Operation, ...]:
        source, operations, _ = self.source(project_id)
        known = {operation.operation_id for operation in operations if operation.supported}
        if any(item not in known for item in selected):
            raise ValueError("selected_operation_not_supported")
        self.save_source(project_id, source, operations, selected)
        return tuple(operation for operation in operations if operation.operation_id in selected)

    def create_release(self, project_id: str, tools: tuple[ToolManifest | ActionToolManifest, ...], profile_id: str | None = None) -> Release:
        serialized = [tool.model_dump(mode="json") for tool in tools]
        manifest_hash = hashlib.sha256(json.dumps(serialized, sort_keys=True).encode()).hexdigest()
        release = Release(
            release_id=secrets.token_urlsafe(9),
            deployment_slug=secrets.token_urlsafe(12),
            project_id=project_id,
            profile_id=profile_id,
            manifest_hash=manifest_hash,
            tools=tools,
            created_at=now(),
        )
        with self._connect() as db:
            db.execute(
                "INSERT INTO releases(release_id,deployment_slug,project_id,manifest_hash,tools_json,created_at,profile_id) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    release.release_id,
                    release.deployment_slug,
                    project_id,
                    manifest_hash,
                    json.dumps(serialized),
                    release.created_at.isoformat(),
                    profile_id,
                ),
            )
        return release

    def put_secret(self, project_id: str, encrypted_value: str | None) -> None:
        with self._connect() as db:
            if encrypted_value is None:
                db.execute("DELETE FROM upstream_secrets WHERE project_id=%s", (project_id,))
                return
            db.execute(
                "INSERT INTO upstream_secrets(project_id,encrypted_value,updated_at) VALUES(%s,%s,%s) "
                "ON CONFLICT(project_id) DO UPDATE SET encrypted_value=excluded.encrypted_value, updated_at=excluded.updated_at",
                (project_id, encrypted_value, now().isoformat()),
            )

    def get_secret(self, project_id: str) -> str | None:
        with self._connect() as db:
            row = db.execute("SELECT encrypted_value FROM upstream_secrets WHERE project_id=%s", (project_id,)).fetchone()
        if row is None:
            return None
        return row["encrypted_value"]

    def release(self, release_id: str | None = None, deployment_slug: str | None = None) -> Release:
        query = "SELECT * FROM releases WHERE release_id=%s" if release_id else "SELECT * FROM releases WHERE deployment_slug=%s"
        value = release_id or deployment_slug
        with self._connect() as db:
            row = db.execute(query, (value,)).fetchone()
        if row is None:
            raise KeyError("release_not_found")
        return Release(
            release_id=row["release_id"],
            deployment_slug=row["deployment_slug"],
            project_id=row["project_id"],
            profile_id=row.get("profile_id"),
            manifest_hash=row["manifest_hash"],
            tools=tuple(_manifest(item) for item in json.loads(row["tools_json"])),
            created_at=row["created_at"],
        )

    @staticmethod
    def _normalize_database_url(database_url: str) -> str:
        parsed = urlsplit(database_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        hostname = parsed.hostname or ""
        if hostname.endswith(".render.com") and "sslmode" not in query:
            query["sslmode"] = "require"
            return urlunsplit(parsed._replace(query=urlencode(query)))
        return database_url

    @staticmethod
    def _project(row: dict[str, Any]) -> Project:
        return Project(
            project_id=row["project_id"],
            name=row["name"],
            base_url=row["base_url"],
            auth_type=row["auth_type"],
            api_key_header=row["api_key_header"],
            created_at=row["created_at"],
        )


def _manifest(value: dict[str, Any]) -> ToolManifest | ActionToolManifest:
    return ActionToolManifest.model_validate(value) if value.get("kind") == "action" else ToolManifest.model_validate(value)
