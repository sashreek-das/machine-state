"""Entity evolution builder.

Extracts per-entity metrics from each snapshot and persists them.
Over time, entities accumulate behavioral history enabling:
- average / peak usage analysis
- growth velocity computation
- launch / presence frequency tracking
- long-term behavioral profiles
"""

from __future__ import annotations

from typing import Any

from .. import store


# ── Recording ─────────────────────────────────────────────────────────────────

def record_snapshot_entities(
    snapshot: dict[str, Any],
    db_path: str | None = None,
) -> dict[str, int]:
    """Extract entity metrics from a snapshot and persist them.

    Returns counts of recorded entities per type.
    """
    timestamp = snapshot.get("timestamp", "")
    entities = snapshot.get("entities", {})
    counts: dict[str, int] = {"applications": 0, "projects": 0, "folders": 0, "processes": 0}

    # Application entities
    for app in entities.get("applications", []):
        entity_id = app.get("entityId", "")
        if not entity_id:
            continue
        metrics = {
            "totalMemoryBytes": int(app.get("totalMemoryBytes") or 0),
            "processCount": int(app.get("processCount") or 0),
        }
        store.save_entity_snapshot(entity_id, "ApplicationEntity", timestamp, metrics, db_path)
        counts["applications"] += 1

    # Project entities
    for project in entities.get("projects", []):
        entity_id = project.get("entityId", "")
        if not entity_id:
            continue
        metrics = {
            "sizeBytes": int(project.get("sizeBytes") or 0),
            "folderCount": len(project.get("folderEntityIds", [])),
        }
        store.save_entity_snapshot(entity_id, "ProjectEntity", timestamp, metrics, db_path)
        counts["projects"] += 1

    # Folder entities
    for folder in entities.get("folders", []):
        entity_id = folder.get("entityId", "")
        if not entity_id:
            continue
        metrics = {
            "sizeBytes": int(folder.get("sizeBytes") or 0),
            "scope": folder.get("scope", ""),
        }
        store.save_entity_snapshot(entity_id, "FolderEntity", timestamp, metrics, db_path)
        counts["folders"] += 1

    return counts


# ── Profile builders ──────────────────────────────────────────────────────────

def _build_numeric_profile(
    history: list[dict[str, Any]],
    metric_key: str,
) -> dict[str, Any]:
    """Compute statistical summary over a numeric metric across history points."""
    values = [
        int(point["metrics"].get(metric_key) or 0)
        for point in history
        if point["metrics"].get(metric_key) is not None
    ]
    if not values:
        return {"available": False}

    first_val = int(history[0]["metrics"].get(metric_key) or 0)
    last_val = int(history[-1]["metrics"].get(metric_key) or 0)
    delta = last_val - first_val
    direction = "flat" if delta == 0 else ("increasing" if delta > 0 else "decreasing")

    return {
        "available": True,
        "observationCount": len(values),
        "averageBytes": int(sum(values) / len(values)),
        "peakBytes": max(values),
        "minimumBytes": min(values),
        "latestBytes": last_val,
        "deltaBytes": delta,
        "direction": direction,
        "firstSeenTimestamp": history[0]["timestamp"],
        "lastSeenTimestamp": history[-1]["timestamp"],
    }


def get_application_profile(
    entity_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Build behavioral profile for an ApplicationEntity."""
    history = store.get_entity_history(entity_id, limit=500, db_path=db_path)
    if not history:
        return {"available": False, "entity_id": entity_id, "reason": "No history recorded."}

    memory_profile = _build_numeric_profile(history, "totalMemoryBytes")
    process_counts = [int(p["metrics"].get("processCount") or 0) for p in history]
    avg_processes = round(sum(process_counts) / len(process_counts), 2) if process_counts else 0

    # Estimate launch frequency: count consecutive appearances
    presence_count = len(history)
    total_observations = presence_count

    return {
        "available": True,
        "entity_id": entity_id,
        "entity_type": "ApplicationEntity",
        "memory": memory_profile,
        "averageProcessCount": avg_processes,
        "peakProcessCount": max(process_counts) if process_counts else 0,
        "presenceCount": presence_count,
        "totalObservations": total_observations,
        "firstSeenTimestamp": history[0]["timestamp"],
        "lastSeenTimestamp": history[-1]["timestamp"],
    }


def get_project_profile(
    entity_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Build behavioral profile for a ProjectEntity."""
    history = store.get_entity_history(entity_id, limit=500, db_path=db_path)
    if not history:
        return {"available": False, "entity_id": entity_id, "reason": "No history recorded."}

    size_profile = _build_numeric_profile(history, "sizeBytes")

    # Growth velocity: bytes per hour
    velocity: float | None = None
    if len(history) >= 2:
        from datetime import datetime
        try:
            t0 = datetime.fromisoformat(history[0]["timestamp"].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(history[-1]["timestamp"].replace("Z", "+00:00"))
            duration_hours = (t1 - t0).total_seconds() / 3600.0
            if duration_hours > 0 and size_profile.get("available"):
                velocity = round(size_profile["deltaBytes"] / duration_hours, 2)
        except (ValueError, KeyError):
            pass

    return {
        "available": True,
        "entity_id": entity_id,
        "entity_type": "ProjectEntity",
        "size": size_profile,
        "growthVelocityBytesPerHour": velocity,
        "observationCount": len(history),
        "firstSeenTimestamp": history[0]["timestamp"],
        "lastSeenTimestamp": history[-1]["timestamp"],
    }


def get_folder_profile(
    entity_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Build behavioral profile for a FolderEntity."""
    history = store.get_entity_history(entity_id, limit=500, db_path=db_path)
    if not history:
        return {"available": False, "entity_id": entity_id, "reason": "No history recorded."}

    size_profile = _build_numeric_profile(history, "sizeBytes")

    velocity: float | None = None
    if len(history) >= 2:
        from datetime import datetime
        try:
            t0 = datetime.fromisoformat(history[0]["timestamp"].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(history[-1]["timestamp"].replace("Z", "+00:00"))
            duration_hours = (t1 - t0).total_seconds() / 3600.0
            if duration_hours > 0 and size_profile.get("available"):
                velocity = round(size_profile["deltaBytes"] / duration_hours, 2)
        except (ValueError, KeyError):
            pass

    scope = history[-1]["metrics"].get("scope", "") if history else ""

    return {
        "available": True,
        "entity_id": entity_id,
        "entity_type": "FolderEntity",
        "scope": scope,
        "size": size_profile,
        "growthVelocityBytesPerHour": velocity,
        "observationCount": len(history),
        "firstSeenTimestamp": history[0]["timestamp"],
        "lastSeenTimestamp": history[-1]["timestamp"],
    }


def get_entity_profile(
    entity_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """Return appropriate profile based on entity_type prefix."""
    history = store.get_entity_history(entity_id, limit=1, db_path=db_path)
    if not history:
        return {"available": False, "entity_id": entity_id, "reason": "No history recorded."}
    entity_type = history[0].get("entity_type", "")
    if entity_type == "ApplicationEntity":
        return get_application_profile(entity_id, db_path)
    if entity_type == "ProjectEntity":
        return get_project_profile(entity_id, db_path)
    if entity_type == "FolderEntity":
        return get_folder_profile(entity_id, db_path)
    # Generic fallback
    full_history = store.get_entity_history(entity_id, limit=500, db_path=db_path)
    return {
        "available": True,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "observationCount": len(full_history),
        "firstSeenTimestamp": full_history[0]["timestamp"] if full_history else None,
        "lastSeenTimestamp": full_history[-1]["timestamp"] if full_history else None,
    }


def list_tracked_entities(db_path: str | None = None) -> list[dict[str, Any]]:
    """Return all entity IDs and types that have recorded history."""
    return store.get_tracked_entity_ids(db_path)
