from __future__ import annotations

import re
from typing import Any

from product_to_mcp.domain.models import Operation


HTTP_METHODS = ("get", "head", "post", "put", "patch", "delete", "options")
SUPPORTED_METHODS = {"get", "head", "post", "put", "patch", "delete"}


def discover_operations(document: dict[str, Any]) -> tuple[Operation, ...]:
    result: list[Operation] = []
    used_names: set[str] = set()
    for path, path_item in document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        path_parameters = tuple(item for item in path_item.get("parameters", ()) if isinstance(item, dict))
        for method in HTTP_METHODS:
            operation_data = path_item.get(method)
            if not isinstance(operation_data, dict):
                continue
            operation_id = str(operation_data.get("operationId") or f"{method}_{path.strip('/').replace('/', '_') or 'root'}")
            name = _safe_name(operation_id, method, path, used_names)
            supported = method in SUPPORTED_METHODS
            reason = None if supported else "Prototype supports GET, HEAD, POST, PUT, PATCH, and DELETE operations."
            parameters = path_parameters + tuple(item for item in operation_data.get("parameters", ()) if isinstance(item, dict))
            result.append(Operation(
                operation_id=operation_id, tool_name=name, method=method.upper(), path=path,
                description=str(operation_data.get("description") or operation_data.get("summary") or f"Call {method.upper()} {path}"),
                input_schema=_input_schema(parameters, operation_data.get("requestBody")), supported=supported, reason=reason,
            ))
    return tuple(result)


def _safe_name(operation_id: str, method: str, path: str, used: set[str]) -> str:
    base = re.sub(r"[^a-zA-Z0-9_]+", "_", operation_id).strip("_").lower() or f"{method}_{path.strip('/').replace('/', '_')}"
    candidate = base
    counter = 2
    while candidate in used:
        candidate = f"{base}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def _input_schema(parameters: tuple[dict[str, Any], ...], request_body: Any = None) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in parameters:
        name = parameter.get("name")
        location = parameter.get("in")
        if not isinstance(name, str) or location not in {"path", "query", "header"}:
            continue
        schema = parameter.get("schema") if isinstance(parameter.get("schema"), dict) else {"type": "string"}
        properties[name] = {**schema, "x-location": location}
        if parameter.get("required") is True or location == "path":
            required.append(name)
    body_schema = _json_body_schema(request_body)
    if body_schema is not None:
        properties["body"] = {**body_schema, "x-location": "body"}
        if isinstance(request_body, dict) and request_body.get("required") is True:
            required.append("body")
    value: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        value["required"] = required
    return value


def _json_body_schema(request_body: Any) -> dict[str, Any] | None:
    if not isinstance(request_body, dict):
        return None
    content = request_body.get("content")
    if not isinstance(content, dict):
        return {"type": "object", "description": "JSON request body"}
    media_type = content.get("application/json") or next((value for key, value in content.items() if str(key).endswith("+json")), None)
    if not isinstance(media_type, dict):
        return {"type": "object", "description": "JSON request body"}
    schema = media_type.get("schema")
    if not isinstance(schema, dict):
        return {"type": "object", "description": "JSON request body"}
    return schema
