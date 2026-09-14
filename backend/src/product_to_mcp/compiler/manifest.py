from __future__ import annotations

from product_to_mcp.actions.validation import derived_annotations, validate_action
from product_to_mcp.domain.models import ActionDefinition, ActionToolManifest, Operation, ToolAnnotations, ToolManifest


def compile_tools(operations: tuple[Operation, ...], selected: tuple[str, ...]) -> tuple[ToolManifest, ...]:
    by_id = {operation.operation_id: operation for operation in operations}
    tools: list[ToolManifest] = []
    for operation_id in selected:
        operation = by_id.get(operation_id)
        if operation is None or not operation.supported:
            raise ValueError("selected_operation_not_supported")
        tools.append(ToolManifest(
            operation_id=operation.operation_id, name=operation.tool_name,
            title=_title(operation.tool_name),
            description=operation.description, method=operation.method,
            path=operation.path, input_schema=operation.input_schema,
            output_schema=operation.output_schema,
            annotations=_operation_annotations(operation),
        ))
    if not tools:
        raise ValueError("at_least_one_operation_required")
    return tuple(tools)


def _operation_annotations(operation: Operation) -> ToolAnnotations:
    read_only = operation.method in {"GET", "HEAD"}
    return ToolAnnotations(
        title=_title(operation.tool_name),
        read_only_hint=read_only,
        destructive_hint=operation.method == "DELETE",
        idempotent_hint=operation.method in {"GET", "HEAD", "PUT", "DELETE"},
        open_world_hint=True,
    )


def _title(name: str) -> str:
    return " ".join(item.capitalize() for item in name.split("_"))


def compile_actions(actions: tuple[ActionDefinition, ...], operations: tuple[Operation, ...], max_steps: int = 10) -> tuple[ActionToolManifest, ...]:
    by_id = {operation.operation_id: operation for operation in operations}
    tools: list[ActionToolManifest] = []
    names: set[str] = set()
    for action in actions:
        if action.status != "approved":
            raise ValueError("all_profile_actions_must_be_approved")
        errors = validate_action(action, operations, max_steps)
        if errors:
            raise ValueError("profile_action_is_invalid")
        if action.name in names:
            raise ValueError("action_names_must_be_unique")
        names.add(action.name)
        snapshot = tuple(by_id[step.operation_id] for step in action.steps)
        tools.append(ActionToolManifest(
            kind="action", action_id=action.action_id, name=action.name, title=action.title,
            description=action.description, input_schema=action.input_schema,
            output_schema=action.output_schema, annotations=derived_annotations(action, by_id),
            steps=action.steps, output_bindings=action.output_bindings, operations=snapshot,
        ))
    if not tools:
        raise ValueError("at_least_one_approved_action_required")
    return tuple(tools)
