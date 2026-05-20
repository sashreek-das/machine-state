"""Dispatch alert fires through the notification layer (Phase 9).

Respects per-rule cooldown_minutes to avoid alert spam.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .evaluator import AlertFire

from .. import store


def _cooldown_key(rule_name: str) -> str:
    return f"alert:{rule_name}"


def _within_cooldown(rule_name: str, cooldown_minutes: int, db_path: object) -> bool:
    last = store.get_last_notification_time(_cooldown_key(rule_name), db_path=db_path)
    if last is None:
        return False
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) - last_dt < timedelta(minutes=cooldown_minutes)
    except ValueError:
        return False


def dispatch_fires(
    fires: list[AlertFire],
    db_path: object = None,
    dry_run: bool = False,
) -> list[str]:
    """Send macOS notifications for alert fires that are not in cooldown.

    Returns list of rule names that fired.
    """
    sent: list[str] = []
    for fire in fires:
        rule = fire.rule
        if _within_cooldown(rule.name, rule.cooldown_minutes, db_path):
            continue
        if not dry_run:
            try:
                from ..notifications.notifier import send_notification
                send_notification("machine state", fire.message)
            except Exception:
                pass
            ts = datetime.now(timezone.utc).isoformat()
            store.save_notification_log(
                ts, _cooldown_key(rule.name), "machine state", fire.message, db_path
            )
        sent.append(rule.name)
    return sent
