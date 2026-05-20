"""Custom user-defined alert rules (Phase 9).

Rules are read from ~/.machine-state/alerts.json.
Evaluated after each scheduler snapshot cycle.
"""

from .loader import load_alert_rules, AlertRule
from .evaluator import evaluate_rules, AlertFire
from .dispatcher import dispatch_fires

__all__ = ["load_alert_rules", "AlertRule", "evaluate_rules", "AlertFire", "dispatch_fires"]
