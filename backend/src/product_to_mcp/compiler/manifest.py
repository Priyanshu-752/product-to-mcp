from __future__ import annotations

from product_to_mcp.domain.models import Operation, ToolManifest


def compile_tools(operations: tuple[Operation, ...], selected: tuple[str, ...]) -> tuple[ToolManifest, ...]:
    by_id = {operation.operation_id: operation for operation in operations}
    tools: list[ToolManifest] = []
    for operation_id in selected:
        operation = by_id.get(operation_id)
        if operation is None or not operation.supported:
            raise ValueError("selected_operation_not_supported")
        tools.append(ToolManifest(
            operation_id=operation.operation_id, name=operation.tool_name,
            description=operation.description, method=operation.method,
            path=operation.path, input_schema=operation.input_schema,
        ))
    if not tools:
        raise ValueError("at_least_one_operation_required")
    return tuple(tools)

