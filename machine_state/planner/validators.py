"""Argument validation against tool contracts.

Validates that a tool call's arguments:
  - contain all required fields
  - contain no disallowed/unknown fields
  - match the declared type
  - satisfy enum constraints
  - satisfy min/max bounds

Returns coerced arguments (with defaults applied) on success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import TOOL_REGISTRY, ParameterSpec


@dataclass
class ValidationError:
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    coerced_args: dict[str, Any] = field(default_factory=dict)

    def first_error(self) -> str | None:
        return str(self.errors[0]) if self.errors else None


# ── Type coercion ──────────────────────────────────────────────────────────────

def _coerce(value: Any, spec: ParameterSpec) -> tuple[Any, str | None]:
    """Coerce value to the declared type. Returns (coerced_value, error_or_None)."""
    t = spec.type
    try:
        if t == "string":
            return str(value), None
        if t == "integer":
            coerced = int(value)
            return coerced, None
        if t == "float":
            coerced = float(value)
            return coerced, None
        if t == "boolean":
            if isinstance(value, bool):
                return value, None
            if isinstance(value, str):
                if value.lower() in ("true", "1", "yes"):
                    return True, None
                if value.lower() in ("false", "0", "no"):
                    return False, None
            return None, f"Cannot coerce '{value}' to boolean"
    except (ValueError, TypeError):
        return None, f"Cannot coerce '{value}' to {t}"
    return None, f"Unknown type '{t}'"


# ── Main validator ─────────────────────────────────────────────────────────────

def validate_arguments(tool_name: str, args: dict[str, Any]) -> ValidationResult:
    """Validate and coerce tool call arguments against the tool's contract.

    Returns a ValidationResult with:
    - valid=True and coerced_args on success
    - valid=False and errors list on failure
    """
    tool = TOOL_REGISTRY.get(tool_name)
    if tool is None:
        return ValidationResult(
            valid=False,
            errors=[ValidationError("tool", f"Unknown tool '{tool_name}'")],
        )

    schema = tool.schema
    errors: list[ValidationError] = []
    coerced: dict[str, Any] = {}

    # Check for unknown parameters
    allowed = set(schema.parameters)
    for key in args:
        if key not in allowed:
            errors.append(ValidationError(key, f"Unknown parameter '{key}'"))

    if errors:
        return ValidationResult(valid=False, errors=errors)

    # Validate each declared parameter
    for param_name, spec in schema.parameters.items():
        raw = args.get(param_name)

        if raw is None:
            if spec.required:
                errors.append(ValidationError(param_name, "Required parameter is missing"))
                continue
            coerced[param_name] = spec.default
            continue

        # Type coercion
        value, err = _coerce(raw, spec)
        if err:
            errors.append(ValidationError(param_name, err))
            continue

        # Enum validation
        if spec.enum is not None and value not in spec.enum:
            errors.append(ValidationError(
                param_name,
                f"Value '{value}' not in allowed values: {spec.enum}",
            ))
            continue

        # Numeric bounds
        if spec.min_value is not None and isinstance(value, (int, float)):
            if value < spec.min_value:
                errors.append(ValidationError(
                    param_name,
                    f"Value {value} is below minimum {spec.min_value}",
                ))
                continue
        if spec.max_value is not None and isinstance(value, (int, float)):
            if value > spec.max_value:
                errors.append(ValidationError(
                    param_name,
                    f"Value {value} exceeds maximum {spec.max_value}",
                ))
                continue

        coerced[param_name] = value

    if errors:
        return ValidationResult(valid=False, errors=errors)

    return ValidationResult(valid=True, coerced_args=coerced)


def validate_plan(steps: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Validate all steps in an execution plan.

    Returns a list of {tool, valid, errors, coerced_args} for each step.
    """
    results = []
    for tool_name, args in steps:
        result = validate_arguments(tool_name, args)
        results.append({
            "tool": tool_name,
            "valid": result.valid,
            "errors": [str(e) for e in result.errors],
            "coerced_args": result.coerced_args,
        })
    return results
