from __future__ import annotations

import httpx
import pytest

from product_to_mcp.actions.executor import ActionExecutor
from product_to_mcp.actions.validation import validate_action
from product_to_mcp.compiler.manifest import compile_actions
from product_to_mcp.domain.models import (
    ActionDefinition, ActionStep, ArgumentBinding, Operation, OutputBinding,
    Project, StepCondition, ValueReference, now,
)
from product_to_mcp.gateway.executor import UpstreamExecutor
from product_to_mcp.openapi.operations import discover_operations
from product_to_mcp.openapi.parser import parse_document
from product_to_mcp.storage.secrets import PrototypeSecretStore


def ref(source: str, path: str | None = None, step: str | None = None, value=None) -> ValueReference:
    return ValueReference(source=source, source_path=path, source_step_id=step, constant_value=value)


def operation(operation_id: str, method: str, path: str, input_schema: dict, output_schema: dict) -> Operation:
    return Operation(
        operation_id=operation_id, tool_name=operation_id.lower(), method=method,
        path=path, description=operation_id, input_schema=input_schema, output_schema=output_schema,
    )


def action(steps: tuple[ActionStep, ...], output_bindings: tuple[OutputBinding, ...] = ()) -> ActionDefinition:
    stamp = now()
    return ActionDefinition(
        action_id="act_test", project_id="project", name="create_verified_product",
        title="Create verified product", description="Create a product and verify the result.",
        input_schema={
            "type": "object", "properties": {"sku": {"type": "string"}, "name": {"type": "string"}},
            "required": ["sku", "name"], "additionalProperties": False,
        },
        output_schema={"type": "object", "properties": {"product_id": {"type": "string"}}, "required": ["product_id"], "additionalProperties": False},
        steps=steps, output_bindings=output_bindings, status="approved", created_at=stamp, updated_at=stamp,
    )


def test_openapi_discovery_adds_groups_responses_refs_and_fingerprints() -> None:
    document = parse_document(b"""
openapi: 3.0.3
info: {title: Catalog, version: '1'}
components:
  schemas:
    Product:
      type: object
      required: [id]
      properties: {id: {type: string}, name: {type: string}}
paths:
  /products/{id}:
    get:
      operationId: getProduct
      tags: [Product Catalog]
      parameters:
        - {name: id, in: path, required: true, schema: {type: string}}
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Product'}
""")
    discovered = discover_operations(document)
    assert discovered[0].default_group == "Product Catalog"
    assert discovered[0].output_schema["properties"]["id"]["type"] == "string"
    assert len(discovered[0].operation_fingerprint) == 64


def test_discovery_handles_fifty_operations() -> None:
    paths = "\n".join(
        f"  /items/{index}:\n    get:\n      operationId: getItem{index}\n      tags: [Items]\n      responses: {{'200': {{description: ok}}}}"
        for index in range(50)
    )
    document = parse_document(f"openapi: 3.0.3\ninfo: {{title: Large, version: '1'}}\npaths:\n{paths}\n".encode())
    discovered = discover_operations(document)
    assert len(discovered) == 50
    assert {item.default_group for item in discovered} == {"Items"}


def test_validation_rejects_multiple_writes_and_future_references() -> None:
    body = {"type": "object", "properties": {"body": {"type": "object", "x-location": "body"}}, "required": ["body"]}
    operations = (
        operation("createProduct", "POST", "/products", body, {"type": "object"}),
        operation("updateProduct", "PATCH", "/products/1", body, {"type": "object"}),
    )
    candidate = action((
        ActionStep(step_id="create", operation_id="createProduct", argument_bindings=(ArgumentBinding(target_path="body", value=ref("previous_step", "data", "update")),)),
        ActionStep(step_id="update", operation_id="updateProduct", argument_bindings=(ArgumentBinding(target_path="body", value=ref("action_input", "name")),)),
    ))
    codes = {item["code"] for item in validate_action(candidate, operations)}
    assert "multiple_writes" in codes
    assert "previous_step_unavailable" in codes


def test_validation_rejects_required_reference_to_skippable_step() -> None:
    read = operation("read", "GET", "/read", {"type": "object", "properties": {}}, {"type": "object", "properties": {"id": {"type": "string"}}})
    use = operation("use", "GET", "/use", {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}, {"type": "object"})
    candidate = action((
        ActionStep(step_id="read", operation_id="read", condition=StepCondition(left=ref("constant", value=False), operator="equals", right=ref("constant", value=True), on_false="skip")),
        ActionStep(step_id="use", operation_id="use", argument_bindings=(ArgumentBinding(target_path="id", value=ref("previous_step", "data.id", "read")),)),
    ))
    codes = {item["code"] for item in validate_action(candidate, (read, use))}
    assert "conditional_step_reference" in codes


@pytest.mark.asyncio
async def test_action_executor_runs_read_write_read_chain_and_maps_output() -> None:
    operations = (
        operation("searchProducts", "GET", "/products", {"type": "object", "properties": {"sku": {"type": "string", "x-location": "query"}}, "required": ["sku"]}, {"type": "object", "properties": {"count": {"type": "integer"}}}),
        operation("createProduct", "POST", "/products", {"type": "object", "properties": {"body": {"type": "object", "properties": {"sku": {"type": "string"}, "name": {"type": "string"}}, "required": ["sku", "name"], "x-location": "body"}}, "required": ["body"]}, {"type": "object", "properties": {"id": {"type": "string"}}}),
        operation("getProduct", "GET", "/products/{id}", {"type": "object", "properties": {"id": {"type": "string", "x-location": "path"}}, "required": ["id"]}, {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}}}),
    )
    candidate = action((
        ActionStep(step_id="search", operation_id="searchProducts", argument_bindings=(ArgumentBinding(target_path="sku", value=ref("action_input", "sku")),)),
        ActionStep(step_id="create", operation_id="createProduct", argument_bindings=(
            ArgumentBinding(target_path="body.sku", value=ref("action_input", "sku")),
            ArgumentBinding(target_path="body.name", value=ref("action_input", "name")),
        ), condition=StepCondition(left=ref("previous_step", "data.count", "search"), operator="equals", right=ref("constant", value=0), on_false="fail", failure_message="SKU already exists.")),
        ActionStep(step_id="verify", operation_id="getProduct", argument_bindings=(ArgumentBinding(target_path="id", value=ref("previous_step", "data.id", "create")),)),
    ), (OutputBinding(target_path="product_id", value=ref("previous_step", "data.id", "verify")),))
    assert validate_action(candidate, operations) == []
    tool = compile_actions((candidate,), operations)[0]
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(f"{request.method} {request.url.path}")
        if request.method == "GET" and request.url.path == "/products":
            return httpx.Response(200, json={"count": 0})
        if request.method == "POST":
            return httpx.Response(201, json={"id": "p-2"})
        return httpx.Response(200, json={"id": "p-2", "name": "Growth"})

    upstream = UpstreamExecutor(PrototypeSecretStore(), transport=httpx.MockTransport(handler))
    project = Project(project_id="project", name="Catalog", base_url="https://api.example.com", auth_type="none", created_at=now())
    result = await ActionExecutor(upstream).call(project, tool, {"sku": "sku-2", "name": "Growth"}, include_trace=True)

    assert result["status"] == "success"
    assert result["data"] == {"product_id": "p-2"}
    assert requests == ["GET /products", "POST /products", "GET /products/p-2"]
    assert len(result["trace"]) == 3


@pytest.mark.asyncio
async def test_optional_binding_is_omitted_when_action_input_is_absent() -> None:
    read = operation(
        "listProducts", "GET", "/products",
        {"type": "object", "properties": {"limit": {"type": "integer", "x-location": "query"}}},
        {"type": "object", "properties": {"count": {"type": "integer"}}},
    )
    candidate = action((ActionStep(
        step_id="list", operation_id="listProducts",
        argument_bindings=(ArgumentBinding(target_path="limit", value=ref("action_input", "limit")),),
    ),)).model_copy(update={
        "input_schema": {"type": "object", "properties": {"limit": {"type": "integer"}}, "additionalProperties": False},
        "output_schema": {"type": "object", "properties": {"count": {"type": "integer"}}},
    })
    tool = compile_actions((candidate,), (read,))[0]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.query == b""
        return httpx.Response(200, json={"count": 2})

    upstream = UpstreamExecutor(PrototypeSecretStore(), transport=httpx.MockTransport(handler))
    project = Project(project_id="project", name="Catalog", base_url="https://api.example.com", auth_type="none", created_at=now())
    result = await ActionExecutor(upstream).call(project, tool, {})

    assert result["status"] == "success"
    assert result["data"] == {"count": 2}


@pytest.mark.asyncio
async def test_write_timeout_is_reported_as_unknown_and_never_retry_safe() -> None:
    write = operation("createProduct", "POST", "/products", {"type": "object", "properties": {}}, {"type": "object"})
    candidate = action((ActionStep(step_id="create", operation_id="createProduct"),))
    candidate = candidate.model_copy(update={
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "output_schema": {"type": "object"},
    })
    tool = compile_actions((candidate,), (write,))[0]

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("unknown", request=request)

    upstream = UpstreamExecutor(PrototypeSecretStore(), transport=httpx.MockTransport(handler))
    project = Project(project_id="project", name="Catalog", base_url="https://api.example.com", auth_type="none", created_at=now())
    result = await ActionExecutor(upstream).call(project, tool, {})

    assert result["status"] == "outcome_unknown"
    assert result["retry_safe"] is False
    assert result["write_may_have_completed"] is True
