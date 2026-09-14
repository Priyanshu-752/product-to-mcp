from __future__ import annotations

import re
import hashlib
import json
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
        path_item = _resolve_object(path_item, document)
        path_parameters = tuple(item for item in path_item.get("parameters", ()) if isinstance(item, dict))
        for method in HTTP_METHODS:
            operation_data = path_item.get(method)
            if not isinstance(operation_data, dict):
                continue
            operation_id = str(operation_data.get("operationId") or f"{method}_{path.strip('/').replace('/', '_') or 'root'}")
            if any(item.operation_id == operation_id for item in result):
                raise ValueError(f"OpenAPI operationId values must be unique: {operation_id}")
            name = _safe_name(operation_id, method, path, used_names)
            supported = method in SUPPORTED_METHODS
            reason = None if supported else "Prototype supports GET, HEAD, POST, PUT, PATCH, and DELETE operations."
            parameters = path_parameters + tuple(item for item in operation_data.get("parameters", ()) if isinstance(item, dict))
            raw_tags = operation_data.get("tags", ())
            tags = tuple(str(item).strip() for item in raw_tags if str(item).strip()) if isinstance(raw_tags, list) else ()
            input_schema = _input_schema(parameters, operation_data.get("requestBody"), document)
            output_schema = _output_schema(operation_data.get("responses"), document)
            default_group = tags[0] if tags else _path_group(path)
            fingerprint = hashlib.sha256(json.dumps({
                "method": method.upper(), "path": path, "input": input_schema, "output": output_schema,
            }, sort_keys=True).encode()).hexdigest()
            result.append(Operation(
                operation_id=operation_id, tool_name=name, method=method.upper(), path=path,
                description=str(operation_data.get("description") or operation_data.get("summary") or f"Call {method.upper()} {path}"),
                input_schema=input_schema, tags=tags, default_group=default_group,
                output_schema=output_schema, operation_fingerprint=fingerprint,
                supported=supported, reason=reason,
            ))
    return tuple(result)


def _safe_name(operation_id: str, method: str, path: str, used: set[str]) -> str:
    base = _to_snake_case(operation_id) or _to_snake_case(f"{method}_{path.strip('/').replace('/', '_')}")
    candidate = base
    counter = 2
    while candidate in used:
        candidate = f"{base}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def _to_snake_case(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_").lower()


def _input_schema(parameters: tuple[dict[str, Any], ...], request_body: Any, document: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in parameters:
        parameter = _resolve_object(parameter, document)
        name = parameter.get("name")
        location = parameter.get("in")
        if not isinstance(name, str) or location not in {"path", "query", "header"}:
            continue
        schema = parameter.get("schema") if isinstance(parameter.get("schema"), dict) else {"type": "string"}
        schema = _resolve_schema(schema, document)
        if parameter.get("description") and isinstance(schema, dict) and "description" not in schema:
            schema = {**schema, "description": str(parameter["description"])}
        properties[name] = {**schema, "x-location": location}
        if parameter.get("required") is True or location == "path":
            required.append(name)
    body_schema = _json_body_schema(request_body, document)
    if body_schema is not None:
        if isinstance(request_body, dict):
            body = _resolve_object(request_body, document)
            if body.get("description") and "description" not in body_schema:
                body_schema = {**body_schema, "description": str(body["description"])}
        properties["body"] = {**body_schema, "x-location": "body"}
        if isinstance(request_body, dict) and request_body.get("required") is True:
            required.append("body")
    value: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        value["required"] = required
    return value


def _json_body_schema(request_body: Any, document: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(request_body, dict):
        return None
    request_body = _resolve_object(request_body, document)
    content = request_body.get("content")
    if not isinstance(content, dict):
        return {"type": "object", "description": "JSON request body"}
    media_type = content.get("application/json") or next((value for key, value in content.items() if str(key).endswith("+json")), None)
    if not isinstance(media_type, dict):
        return {"type": "object", "description": "JSON request body"}
    schema = media_type.get("schema")
    if not isinstance(schema, dict):
        return {"type": "object", "description": "JSON request body"}
    return _resolve_schema(schema, document)


def _output_schema(responses: Any, document: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(responses, dict):
        return {"type": "object"}
    candidates = sorted((str(code), value) for code, value in responses.items() if str(code).startswith("2"))
    for _, raw_response in candidates:
        if not isinstance(raw_response, dict):
            continue
        response = _resolve_object(raw_response, document)
        content = response.get("content")
        if not isinstance(content, dict):
            continue
        media = content.get("application/json") or next(
            (value for key, value in content.items() if str(key).endswith("+json")), None
        )
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            return _resolve_schema(media["schema"], document)
    return {"type": "object"}


def _path_group(path: str) -> str:
    segment = next((item for item in path.strip("/").split("/") if item and not item.startswith("{")), "General")
    if segment == "General":
        return segment
    return " ".join(word.capitalize() for word in re.split(r"[-_]", segment) if word) or "General"


def _resolve_object(value: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    reference = value.get("$ref")
    if not isinstance(reference, str):
        return value
    resolved = _resolve_reference(reference, document)
    return {**resolved, **{key: item for key, item in value.items() if key != "$ref"}}


def _resolve_schema(value: Any, document: dict[str, Any], seen: tuple[str, ...] = ()) -> Any:
    if isinstance(value, list):
        return [_resolve_schema(item, document, seen) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    if isinstance(reference, str):
        if reference in seen:
            return {"type": "object", "description": f"Recursive reference: {reference}"}
        resolved = _resolve_reference(reference, document)
        merged = {**resolved, **{key: item for key, item in value.items() if key != "$ref"}}
        return _resolve_schema(merged, document, (*seen, reference))
    return {key: _resolve_schema(item, document, seen) for key, item in value.items()}


def _resolve_reference(reference: str, document: dict[str, Any]) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise ValueError("Remote OpenAPI references are not supported.")
    current: Any = document
    for segment in reference[2:].split("/"):
        key = segment.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"OpenAPI reference not found: {reference}")
        current = current[key]
    if not isinstance(current, dict):
        raise ValueError(f"OpenAPI reference must resolve to an object: {reference}")
    return current
