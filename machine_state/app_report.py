"""Per-application behavioural profile aggregated from entity history (Phase 9).

All data comes from existing SQLite tables — no new collection.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import store
from .constants import GB, MB


def _norm(name: str) -> str:
    return name.lower().replace(" ", "").replace("-", "")


def _find_entity_id(name: str, all_ids: list[dict[str, Any]]) -> str | None:
    target = _norm(name)
    for row in all_ids:
        eid = row["entity_id"]
        if eid.startswith("application:"):
            if _norm(eid.replace("application:", "")) == target:
                return row["entity_id"]
    return None


def _fmt_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m"


def _ram_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    mems = [int(h["metrics"].get("totalMemoryBytes") or 0) for h in history]
    mems = [m for m in mems if m > 0]
    if not mems:
        return {}
    return {
        "avgBytes": int(sum(mems) / len(mems)),
        "peakBytes": max(mems),
        "observations": len(mems),
    }


def _session_stats(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate sessions from gaps in appearance timestamps."""
    if not history:
        return {"count": 0}
    timestamps = []
    for h in history:
        try:
            ts = datetime.fromisoformat(h["timestamp"].replace("Z", "+00:00"))
            timestamps.append(ts)
        except ValueError:
            pass
    if len(timestamps) < 2:
        return {"count": 1}
    timestamps.sort()
    sessions = 1
    durations: list[float] = []
    session_start = timestamps[0]
    for i in range(1, len(timestamps)):
        gap = (timestamps[i] - timestamps[i - 1]).total_seconds()
        if gap > 1800:  # 30-min gap = new session
            durations.append((timestamps[i - 1] - session_start).total_seconds())
            sessions += 1
            session_start = timestamps[i]
    durations.append((timestamps[-1] - session_start).total_seconds())
    avg_dur = sum(durations) / len(durations) if durations else 0
    return {
        "count": sessions,
        "avgDurationSeconds": int(avg_dur),
        "avgDurationLabel": _fmt_duration(avg_dur),
        "longestSeconds": int(max(durations)) if durations else 0,
        "longestLabel": _fmt_duration(max(durations)) if durations else "—",
    }


def _event_stats(app_name: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    target = _norm(app_name)
    related = [
        e for e in events
        if target in _norm(e.get("summary", ""))
    ]
    critical = sum(1 for e in related if e.get("severity") == "critical")
    return {"relatedEvents": len(related), "criticalEvents": critical}


def get_app_report(
    app_name: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Return a structured behavioural profile for app_name.

    Raises ValueError if the application has no recorded history.
    """
    from pathlib import Path
    all_ids = store.get_tracked_entity_ids(db_path=db_path)
    entity_id = _find_entity_id(app_name, all_ids)
    if entity_id is None:
        raise ValueError(
            f"No entity history found for {app_name!r}. "
            "Run `machine-state entity-history` to list tracked applications."
        )

    history = store.get_entity_history(entity_id, limit=500, db_path=db_path)
    all_events = store.get_events(limit=500, db_path=db_path)

    ram = _ram_history(history)
    sessions = _session_stats(history)
    event_s = _event_stats(app_name, all_events)

    first_seen = history[0]["timestamp"] if history else None
    last_seen  = history[-1]["timestamp"] if history else None

    return {
        "application": app_name,
        "entityId": entity_id,
        "firstSeen": first_seen,
        "lastSeen": last_seen,
        "ram": ram,
        "sessions": sessions,
        "events": event_s,
    }
