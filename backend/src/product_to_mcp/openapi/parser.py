from __future__ import annotations

import json
from typing import Any

import yaml

from product_to_mcp.domain.errors import ValidationError


def parse_document(content: bytes) -> dict[str, Any]:
    if not content:
        raise ValidationError("The OpenAPI document is empty.")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError("The OpenAPI document must be UTF-8.") from error
    try:
        value = json.loads(text) if text.lstrip().startswith(("{", "[")) else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise ValidationError(f"The OpenAPI document could not be parsed: {error}") from error
    if not isinstance(value, dict) or not value.get("openapi"):
        raise ValidationError("A valid OpenAPI 3.x document is required.")
    if not str(value["openapi"]).startswith("3."):
        raise ValidationError("Only OpenAPI 3.0 and 3.1 are supported by the prototype.")
    if not isinstance(value.get("paths"), dict):
        raise ValidationError("The OpenAPI document must contain a paths object.")
    return value

