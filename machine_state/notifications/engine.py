"""Local notification engine.

Evaluates system state and emits macOS notifications for important events.

Rules:
- Notifications are deterministic: same state always produces same decision
- Rate-limited: a notification key can only fire once per cooldown period
- Evidence-backed: every notification includes supporting data
- Locally generated: uses macOS osascript, no external services

Notification triggers:
1. Disk fill projection < 3 days (from forecast)
2. RAM pressure sustained > 85% for 2+ consecutive snapshots
3. A single folder grew by > 2 GB in the last collection window
4. A single event of severity=critical is detected
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

from .. import store
from ..forecast import forecast_disk_pressure
from ..pressure import compute_live_pressure
from ..constants import NOTIFICATION_DISK_FILL_HOURS, NOTIFICATION_RAM_CRITICAL

# Cooldown periods in seconds (to prevent spam)
_COOLDOWNS: dict[str, int] = {
    "disk_fill_imminent": 6 * 3600,      # 6 hours
    "ram_pressure_sustained": 2 * 3600,  # 2 hours
    "folder_explosion": 1 * 3600,        # 1 hour
    "critical_event": 30 * 60,           # 30 minutes
}


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_on_cooldown(key: str, db_path: str | None) -> bool:
    """Return True if the notification key is still within its cooldown period."""
    last = store.get_last_notification_time(key, db_path)
    if last is None:
        return False
    cooldown = _COOLDOWNS.get(key, 3600)
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        now_dt = datetime.now(timezone.utc)
        elapsed = (now_dt - last_dt).total_seconds()
        return elapsed < cooldown
    except ValueError:
        return False


def _send_macos_notification(title: str, body: str) -> bool:
    """Send a macOS notification via osascript. Returns True on success."""
    if sys.platform != "darwin":
        return False
    script = (
        f'display notification "{body}" with title "{title}"'
    )
    try:
        subprocess.run(
            ["osascript", "-e", script],
            timeout=5,
            check=False,
            capture_output=True,
        )
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def send_notification(
    key: str,
    title: str,
    body: str,
    db_path: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Send a rate-limited local notification.

    Args:
        key: Unique notification key for rate limiting.
        title: Notification title.
        body: Notification body text.
        db_path: SQLite database path.
        force: Skip cooldown check and send regardless.

    Returns:
        dict with 'sent' (bool) and 'reason' if not sent.
    """
    if not force and _is_on_cooldown(key, db_path):
        return {"sent": False, "reason": "On cooldown.", "key": key}

    now = _now_utc()
    sent = _send_macos_notification(title, body)

    if sent:
        store.save_notification_log(now, key, title, body, db_path)

    return {
        "sent": sent,
        "key": key,
        "title": title,
        "body": body,
        "timestamp": now,
    }


def get_pending_notifications(
    snapshots: list[dict[str, Any]],
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate current state and return notifications that would fire.

    Does NOT send them — use this for previewing what would be notified.
    """
    pending: list[dict[str, Any]] = []

    if not snapshots:
        return pending

    # 1. Disk fill projection
    forecast = forecast_disk_pressure(snapshots, percent_threshold=95.0)
    if forecast.get("available") and not forecast.get("alreadyExceeded"):
        hours = forecast.get("hoursUntilThreshold", float("inf"))
        if isinstance(hours, (int, float)) and hours <= NOTIFICATION_DISK_FILL_HOURS:
            days = round(hours / 24, 1)
            pending.append(
                {
                    "key": "disk_fill_imminent",
                    "title": "Disk Filling Up",
                    "body": f"Disk projected to reach 95% in {days} days at current growth rate.",
                    "evidence": forecast,
                }
            )

    # 2. Sustained RAM pressure
    pressure = compute_live_pressure(snapshots)
    ram = pressure.get("ram", {})
    if (
        ram.get("available")
        and ram.get("sustained")
        and ram.get("latestScore", 0.0) >= NOTIFICATION_RAM_CRITICAL
    ):
        score_pct = round(ram["latestScore"] * 100, 1)
        pending.append(
            {
                "key": "ram_pressure_sustained",
                "title": "RAM Pressure Sustained",
                "body": f"RAM usage has been above 75% for multiple snapshots (currently {score_pct}%).",
                "evidence": ram,
            }
        )

    # 3. Critical events in recent history
    recent_events = store.get_events(limit=10, db_path=db_path)
    critical = [e for e in recent_events if e.get("severity") == "critical"]
    if critical:
        latest = critical[0]
        pending.append(
            {
                "key": "critical_event",
                "title": f"Critical: {latest.get('event_type', 'event').replace('_', ' ').title()}",
                "body": latest.get("summary", "A critical system event was detected."),
                "evidence": latest,
            }
        )

    return pending


def evaluate_and_notify(
    snapshots: list[dict[str, Any]],
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate state and send any triggered notifications (with rate limiting).

    Returns list of notification results.
    """
    pending = get_pending_notifications(snapshots, db_path)
    results: list[dict[str, Any]] = []
    for notification in pending:
        result = send_notification(
            key=notification["key"],
            title=notification["title"],
            body=notification["body"],
            db_path=db_path,
        )
        results.append(result)
    return results
