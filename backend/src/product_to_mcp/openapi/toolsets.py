from __future__ import annotations

import hashlib
import re

from product_to_mcp.domain.models import Operation


def derived_toolsets(operations: tuple[Operation, ...]) -> list[dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for operation in operations:
        if not operation.supported:
            continue
        label = (operation.default_group or "General").strip() or "General"
        key = " ".join(label.casefold().split())
        toolset_id = f"ts_{re.sub(r'[^a-z0-9]+', '_', key).strip('_')[:40] or 'general'}_{hashlib.sha256(key.encode()).hexdigest()[:8]}"
        if toolset_id not in result:
            result[toolset_id] = {
                "toolset_id": toolset_id, "name": label, "operation_ids": [],
                "read_count": 0, "write_count": 0,
            }
        item = result[toolset_id]
        item["operation_ids"].append(operation.operation_id)
        item["read_count" if operation.method in {"GET", "HEAD"} else "write_count"] += 1
    return list(result.values())


def available_toolsets(operations: tuple[Operation, ...], custom: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    result = derived_toolsets(operations)
    supported = {item.operation_id: item for item in operations if item.supported}
    for item in custom:
        members = [supported[operation_id] for operation_id in item["operation_ids"] if operation_id in supported]
        result.append({
            "toolset_id": item["toolset_id"], "name": item["name"], "custom": True,
            "operation_ids": [member.operation_id for member in members],
            "read_count": sum(member.method in {"GET", "HEAD"} for member in members),
            "write_count": sum(member.method not in {"GET", "HEAD"} for member in members),
            "needs_review": len(members) != len(item["operation_ids"]),
        })
    return result


def resolve_toolset_operations(
    operations: tuple[Operation, ...], selected_toolset_ids: tuple[str, ...] | None,
    custom: tuple[dict[str, object], ...] = (),
) -> tuple[str, ...]:
    toolsets = available_toolsets(operations, custom)
    if selected_toolset_ids is None:
        return tuple(operation.operation_id for operation in operations if operation.supported)
    known = {item["toolset_id"]: item for item in toolsets}
    if len(selected_toolset_ids) != len(set(selected_toolset_ids)):
        raise ValueError("Toolset IDs must be unique.")
    if any(item not in known for item in selected_toolset_ids):
        raise ValueError("A selected toolset is unavailable in the current OpenAPI source. Review the toolsets and try again.")
    if any(known[item].get("needs_review") for item in selected_toolset_ids):
        raise ValueError("A custom toolset contains operations missing from the current OpenAPI source. Edit and review it before releasing.")
    selected = set(selected_toolset_ids)
    operation_ids = {operation_id for toolset_id in selected for operation_id in known[toolset_id]["operation_ids"]}
    return tuple(operation.operation_id for operation in operations if operation.supported and operation.operation_id in operation_ids)
