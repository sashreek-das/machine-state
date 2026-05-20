"""Evaluate alert rules against current machine state (Phase 9).

All evaluation is deterministic: same snapshot + rules → same fires.
No subprocess calls, no side effects.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Any

from .loader import AlertRule
from ..constants import GB

_OPS: dict[str, Any] = {
    ">": operator.gt, "<": operator.lt,
    ">=": operator.ge, "<=": operator.le,
    "==": operator.eq,
}


@dataclass
class AlertFire:
    rule: AlertRule
    message: str
    current_value: float


def _extract_vars(snapshot: dict[str, Any], health_score: int) -> dict[str, float]:
    ram  = snapshot.get("system", {}).get("ram", {})
    disk = snapshot.get("system", {}).get("disk", {})
    total_ram  = int(ram.get("totalBytes") or 0)
    used_ram   = int(ram.get("usedBytes") or 0)
    total_disk = int(disk.get("totalBytes") or 0)
    used_disk  = int(disk.get("usedBytes") or 0)
    free_disk  = total_disk - used_disk
    return {
        "ram_ratio":    used_ram / total_ram if total_ram else 0.0,
        "disk_ratio":   used_disk / total_disk if total_disk else 0.0,
        "disk_free_gb": free_disk / GB,
        "health_score": float(health_score),
    }


def _format_message(template: str, ctx: dict[str, float]) -> str:
    try:
        return template.format(**ctx)
    except (KeyError, ValueError):
        return template


def evaluate_rules(
    rules: list[AlertRule],
    snapshot: dict[str, Any],
    health_score: int,
) -> list[AlertFire]:
    """Return a fire for each rule whose condition is satisfied."""
    if not rules or not snapshot:
        return []
    ctx = _extract_vars(snapshot, health_score)
    fires: list[AlertFire] = []
    for rule in rules:
        op_fn = _OPS.get(rule.op)
        if op_fn is None:
            continue
        current = ctx.get(rule.var, 0.0)
        if op_fn(current, rule.threshold):
            fires.append(AlertFire(
                rule=rule,
                message=_format_message(rule.message, ctx),
                current_value=current,
            ))
    return fires
