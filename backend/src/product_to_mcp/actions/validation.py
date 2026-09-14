from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from product_to_mcp.domain.models import ActionDefinition, Operation, ToolAnnotations, ValueReference


READ_METHODS = {"GET", "HEAD"}


def derived_annotations(action: ActionDefinition, operations: dict[str, Operation]) -> ToolAnnotations:
    methods = [operations[step.operation_id].method for step in action.steps if step.operation_id in operations]
    read_only = bool(methods) and all(method in READ_METHODS for method in methods)
    destructive = "DELETE" in methods
    return ToolAnnotations(
        title=action.title,
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=read_only,
        openWorldHint=True,
    )


def validate_action(action: ActionDefinition, operations: tuple[Operation, ...], max_steps: int = 10) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    by_id = {item.operation_id: item for item in operations}
    _check_schema(action.input_schema, "input_schema", errors)
    _check_schema(action.output_schema, "output_schema", errors)

    if not action.steps:
        _error(errors, "steps", "at_least_one_step", "An action needs at least one API step.")
    if len(action.steps) > max_steps:
        _error(errors, "steps", "too_many_steps", f"An action can contain at most {max_steps} steps.")

    seen_steps: set[str] = set()
    step_schemas: dict[str, dict[str, Any]] = {}
    conditionally_skipped: set[str] = set()
    write_count = 0
    for index, step in enumerate(action.steps):
        path = f"steps.{index}"
        if step.step_id in seen_steps:
            _error(errors, f"{path}.step_id", "duplicate_step_id", "Step IDs must be unique.")
        operation = by_id.get(step.operation_id)
        if operation is None or not operation.supported:
            _error(errors, f"{path}.operation_id", "operation_unavailable", "The selected API operation is unavailable.")
        else:
            if operation.method not in READ_METHODS:
                write_count += 1
            required = operation.input_schema.get("required", [])
            targets = {binding.target_path for binding in step.argument_bindings}
            for name in required:
                if not any(target == name or target.startswith(f"{name}.") for target in targets):
                    _error(errors, f"{path}.argument_bindings", "required_mapping_missing", f"Required API argument '{name}' is not mapped.")
            _check_target_conflicts(targets, path, errors)
            for binding_index, binding in enumerate(step.argument_bindings):
                if not _schema_has_path(operation.input_schema, binding.target_path):
                    _error(errors, f"{path}.argument_bindings.{binding_index}.target_path", "target_path_unknown", f"API input path '{binding.target_path}' does not exist.")

        for binding_index, binding in enumerate(step.argument_bindings):
            _validate_reference(binding.value, seen_steps, conditionally_skipped, action.input_schema, step_schemas, f"{path}.argument_bindings.{binding_index}", errors)
        if step.condition:
            _validate_reference(step.condition.left, seen_steps, conditionally_skipped, action.input_schema, step_schemas, f"{path}.condition.left", errors)
            if step.condition.right:
                _validate_reference(step.condition.right, seen_steps, conditionally_skipped, action.input_schema, step_schemas, f"{path}.condition.right", errors)
            if step.condition.on_false == "skip":
                conditionally_skipped.add(step.step_id)
        seen_steps.add(step.step_id)
        if operation is not None:
            step_schemas[step.step_id] = {"type": "object", "properties": {"data": operation.output_schema}}

    if write_count > 1:
        _error(errors, "steps", "multiple_writes", "A chain can contain at most one write operation.")

    output_targets = {binding.target_path for binding in action.output_bindings}
    _check_target_conflicts(output_targets, "output_bindings", errors)
    for index, binding in enumerate(action.output_bindings):
        _validate_reference(binding.value, seen_steps, conditionally_skipped, action.input_schema, step_schemas, f"output_bindings.{index}", errors)
        if not _schema_has_path(action.output_schema, binding.target_path):
            _error(errors, f"output_bindings.{index}.target_path", "output_path_unknown", f"Output path '{binding.target_path}' does not exist in the action data schema.")
    if action.output_bindings:
        for required_name in action.output_schema.get("required", []):
            if not any(target == required_name or target.startswith(f"{required_name}.") for target in output_targets):
                _error(errors, "output_bindings", "required_output_missing", f"Required output field '{required_name}' is not mapped.")
    return errors


def _check_schema(schema: dict[str, Any], path: str, errors: list[dict[str, str]]) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as error:
        _error(errors, path, "invalid_json_schema", str(error).splitlines()[0])


def _check_target_conflicts(targets: set[str], path: str, errors: list[dict[str, str]]) -> None:
    ordered = sorted(targets)
    for index, target in enumerate(ordered):
        for other in ordered[index + 1:]:
            if other.startswith(f"{target}."):
                _error(errors, path, "overlapping_target", f"'{target}' overlaps with '{other}'.")


def _validate_reference(reference: ValueReference, available: set[str], skipped: set[str], input_schema: dict[str, Any], step_schemas: dict[str, dict[str, Any]], path: str, errors: list[dict[str, str]]) -> None:
    if reference.source == "action_input" and not reference.source_path:
        _error(errors, path, "input_path_required", "Action-input references need a source path.")
    elif reference.source == "action_input" and not _schema_has_path(input_schema, reference.source_path or ""):
        _error(errors, path, "input_path_unknown", f"Action input path '{reference.source_path}' does not exist.")
    if reference.source == "previous_step":
        if not reference.source_step_id or reference.source_step_id not in available:
            _error(errors, path, "previous_step_unavailable", "References may target only an earlier step.")
        elif reference.source_step_id in skipped:
            _error(errors, path, "conditional_step_reference", "A required mapping cannot use a step that may be skipped.")
        if not reference.source_path:
            _error(errors, path, "step_path_required", "Previous-step references need a source path.")
        elif reference.source_step_id in step_schemas and not _schema_has_path(step_schemas[reference.source_step_id or ""], reference.source_path):
            _error(errors, path, "step_path_unknown", f"Step output path '{reference.source_path}' does not exist.")


def _schema_has_path(schema: dict[str, Any], path: str) -> bool:
    if not path:
        return True
    current: Any = schema
    for part in path.split("."):
        if not isinstance(current, dict):
            return False
        if current.get("type") == "array":
            if not part.isdigit():
                return False
            current = current.get("items", {})
            continue
        properties = current.get("properties")
        if isinstance(properties, dict) and part in properties:
            current = properties[part]
        elif current.get("additionalProperties") is not False:
            return True
        else:
            return False
    return True


def _error(errors: list[dict[str, str]], path: str, code: str, message: str) -> None:
    errors.append({"path": path, "code": code, "message": message})
