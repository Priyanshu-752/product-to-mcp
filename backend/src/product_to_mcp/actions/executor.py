from __future__ import annotations

import asyncio
import time
from typing import Any

from jsonschema import ValidationError, validate

from product_to_mcp.domain.models import ActionToolManifest, Project, ValueReference
from product_to_mcp.gateway.executor import UpstreamExecutor


class ActionExecutor:
    def __init__(self, upstream: UpstreamExecutor, total_timeout: float = 60) -> None:
        self.upstream = upstream
        self.total_timeout = total_timeout

    async def call(self, project: Project, tool: ActionToolManifest, arguments: dict[str, Any], include_trace: bool = False) -> dict[str, Any]:
        try:
            validate(arguments, tool.input_schema)
        except ValidationError as error:
            return self._result("rejected", False, True, error=f"Invalid action input: {error.message}")
        try:
            return await asyncio.wait_for(self._run(project, tool, arguments, include_trace), timeout=self.total_timeout)
        except TimeoutError:
            contains_write = any(item.method not in {"GET", "HEAD"} for item in tool.operations)
            return self._result(
                "outcome_unknown" if contains_write else "failed", False, not contains_write,
                error="The action exceeded its total execution timeout.", write_may_have_completed=contains_write,
            )

    async def _run(self, project: Project, tool: ActionToolManifest, arguments: dict[str, Any], include_trace: bool) -> dict[str, Any]:
        operations = {item.operation_id: item for item in tool.operations}
        outputs: dict[str, dict[str, Any]] = {}
        trace: list[dict[str, Any]] = []
        write_completed = False
        last_data: Any = {}

        for step in tool.steps:
            started = time.monotonic()
            if step.condition and not _condition_matches(step.condition, arguments, outputs):
                if step.condition.on_false == "fail":
                    trace.append({"step_id": step.step_id, "status": "rejected", "duration_ms": _duration(started)})
                    return self._result("rejected", False, True, error=step.condition.failure_message, failed_step=step.step_id, trace=trace if include_trace else None)
                outputs[step.step_id] = {"ok": True, "skipped": True, "data": {}}
                trace.append({"step_id": step.step_id, "status": "skipped", "duration_ms": _duration(started)})
                continue

            operation = operations[step.operation_id]
            try:
                step_arguments: dict[str, Any] = {}
                for binding in step.argument_bindings:
                    try:
                        value = _resolve(binding.value, arguments, outputs)
                    except KeyError:
                        if not _schema_path_required(operation.input_schema, binding.target_path):
                            continue
                        raise
                    _set_path(step_arguments, binding.target_path, value)
            except (KeyError, TypeError) as error:
                trace.append({"step_id": step.step_id, "status": "mapping_failed", "duration_ms": _duration(started)})
                status = "partial_success" if write_completed else "failed"
                return self._result(status, False, not write_completed, error=f"Step mapping failed: {error}", failed_step=step.step_id, write_may_have_completed=write_completed, trace=trace if include_trace else None)

            is_write = operation.method not in {"GET", "HEAD"}
            result = await self.upstream.call_operation(project, operation, step_arguments)
            trace.append({
                "step_id": step.step_id,
                "operation_id": step.operation_id,
                "status": "success" if result.get("ok") else "failed",
                "status_code": result.get("status_code"),
                "duration_ms": _duration(started),
            })
            if not result.get("ok"):
                if is_write and result.get("outcome_unknown"):
                    return self._result("outcome_unknown", False, False, error=result.get("error"), failed_step=step.step_id, write_may_have_completed=True, trace=trace if include_trace else None)
                status = "partial_success" if write_completed else ("rejected" if result.get("status_code") == 409 else "failed")
                return self._result(status, False, not write_completed and not is_write, error=result.get("error"), failed_step=step.step_id, write_may_have_completed=write_completed, trace=trace if include_trace else None, retry_after=result.get("retry_after"))
            if is_write:
                write_completed = True
            outputs[step.step_id] = result
            last_data = result.get("data")

        try:
            data: Any = {}
            if tool.output_bindings:
                for binding in tool.output_bindings:
                    _set_path(data, binding.target_path, _resolve(binding.value, arguments, outputs))
            else:
                data = last_data
            validate(data, tool.output_schema)
        except (KeyError, TypeError, ValidationError) as error:
            status = "partial_success" if write_completed else "failed"
            return self._result(status, False, not write_completed, error=f"Action output could not be created: {error}", write_may_have_completed=write_completed, trace=trace if include_trace else None)
        return self._result("success", True, True, data=data, trace=trace if include_trace else None)

    @staticmethod
    def _result(status: str, ok: bool, retry_safe: bool, **values: Any) -> dict[str, Any]:
        result = {"ok": ok, "status": status, "retry_safe": retry_safe}
        result.update({key: value for key, value in values.items() if value is not None})
        return result


def _resolve(reference: ValueReference, inputs: dict[str, Any], outputs: dict[str, dict[str, Any]]) -> Any:
    if reference.source == "constant":
        return reference.constant_value
    root: Any = inputs if reference.source == "action_input" else outputs[reference.source_step_id or ""]
    return _get_path(root, reference.source_path or "")


def _get_path(value: Any, path: str) -> Any:
    current = value
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = target
    for part in parts[:-1]:
        existing = current.setdefault(part, {})
        if not isinstance(existing, dict):
            raise TypeError(f"Mapping target '{path}' overlaps another value.")
        current = existing
    current[parts[-1]] = value


def _schema_path_required(schema: dict[str, Any], path: str) -> bool:
    current: Any = schema
    for part in path.split("."):
        if not isinstance(current, dict):
            return False
        if part not in current.get("required", []):
            return False
        properties = current.get("properties", {})
        current = properties.get(part, {}) if isinstance(properties, dict) else {}
    return True


def _condition_matches(condition: Any, inputs: dict[str, Any], outputs: dict[str, dict[str, Any]]) -> bool:
    try:
        left = _resolve(condition.left, inputs, outputs)
    except KeyError:
        left = None
    operator = condition.operator
    if operator == "exists": return left is not None
    if operator == "not_exists": return left is None
    if operator == "empty": return left in (None, "", [], {})
    if operator == "not_empty": return left not in (None, "", [], {})
    right = _resolve(condition.right, inputs, outputs) if condition.right else None
    if operator == "equals": return left == right
    if operator == "not_equals": return left != right
    try:
        if operator == "greater_than": return left > right
        if operator == "greater_than_or_equal": return left >= right
        if operator == "less_than": return left < right
        if operator == "less_than_or_equal": return left <= right
    except TypeError:
        return False
    return False


def _duration(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
