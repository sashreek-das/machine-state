"""Load and validate user alert rules from ~/.machine-state/alerts.json (Phase 9).

Example alerts.json:
[
  {
    "name": "RAM critical",
    "condition": "ram_ratio > 0.90",
    "message": "RAM usage is critical.",
    "cooldown_minutes": 60
  },
  {
    "name": "disk almost full",
    "condition": "disk_free_gb < 20",
    "message": "Only {disk_free_gb:.1f} GB remaining on disk.",
    "cooldown_minutes": 1440
  }
]

Supported condition variables:
  ram_ratio        float  (used/total RAM, 0–1)
  disk_ratio       float  (used/total disk, 0–1)
  disk_free_gb     float  (free disk in GB)
  health_score     int    (0–100)

Supported operators in condition: >, <, >=, <=, ==
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_RULES_FILE = Path.home() / ".machine-state" / "alerts.json"

_ALLOWED_VARS = frozenset(["ram_ratio", "disk_ratio", "disk_free_gb", "health_score"])
_ALLOWED_OPS  = frozenset([">", "<", ">=", "<=", "=="])


@dataclass
class AlertRule:
    name: str
    condition: str
    message: str
    cooldown_minutes: int = 60
    _var: str = field(init=False, repr=False)
    _op: str  = field(init=False, repr=False)
    _val: float = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._var, self._op, self._val = _parse_condition(self.condition)

    @property
    def var(self) -> str:
        return self._var

    @property
    def op(self) -> str:
        return self._op

    @property
    def threshold(self) -> float:
        return self._val


def _parse_condition(condition: str) -> tuple[str, str, float]:
    """Parse 'var op value' into (var, op, float). Raises ValueError on invalid input."""
    for op in (">=", "<=", ">", "<", "=="):
        if op in condition:
            parts = condition.split(op, 1)
            var = parts[0].strip()
            val_str = parts[1].strip()
            if var not in _ALLOWED_VARS:
                raise ValueError(f"Unknown variable {var!r}. Allowed: {sorted(_ALLOWED_VARS)}")
            return var, op, float(val_str)
    raise ValueError(f"No valid operator in condition {condition!r}. Allowed: {sorted(_ALLOWED_OPS)}")


def load_alert_rules(path: Path | None = None) -> list[AlertRule]:
    """Load alert rules from JSON. Returns empty list if file doesn't exist."""
    rules_path = path or _RULES_FILE
    if not rules_path.exists():
        return []
    try:
        raw = json.loads(rules_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"alerts.json is not valid JSON: {exc}") from exc

    rules: list[AlertRule] = []
    for item in raw:
        try:
            rules.append(AlertRule(
                name=item["name"],
                condition=item["condition"],
                message=item.get("message", item["name"]),
                cooldown_minutes=int(item.get("cooldown_minutes", 60)),
            ))
        except (KeyError, ValueError) as exc:
            pass  # skip malformed rules rather than crashing the scheduler
    return rules
