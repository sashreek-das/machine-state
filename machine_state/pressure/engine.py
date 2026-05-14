"""Live pressure engine.

Aggregates recent snapshots to determine sustained system pressure state.
A pressure condition is only declared if it persists across multiple
consecutive snapshots, reducing false positives from transient spikes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..constants import (
    RAM_PRESSURE_MODERATE,
    RAM_PRESSURE_HIGH,
    RAM_PRESSURE_CRITICAL,
    DISK_PRESSURE_MODERATE,
    DISK_PRESSURE_HIGH,
    DISK_PRESSURE_CRITICAL,
    SUSTAINED_PRESSURE_RATIO,
    PRESSURE_WINDOW_SIZE,
    TOP_PROCESS_CONTRIBUTORS,
)


def _pressure_level(score: float) -> str:
    if score >= RAM_PRESSURE_CRITICAL:
        return "critical"
    if score >= RAM_PRESSURE_HIGH:
        return "high"
    if score >= RAM_PRESSURE_MODERATE:
        return "moderate"
    return "low"


def _disk_pressure_level(score: float) -> str:
    if score >= DISK_PRESSURE_CRITICAL:
        return "critical"
    if score >= DISK_PRESSURE_HIGH:
        return "high"
    if score >= DISK_PRESSURE_MODERATE:
        return "moderate"
    return "low"


def compute_pressure_level(score: float | None, domain: str = "ram") -> str:
    """Convert a pressure score to a human-readable level string."""
    if score is None:
        return "unknown"
    if domain == "disk":
        return _disk_pressure_level(score)
    return _pressure_level(score)


def _ram_pressure_analysis(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute sustained RAM pressure from recent snapshots."""
    scores: list[float] = []
    for snapshot in snapshots:
        ram = snapshot.get("system", {}).get("ram", {})
        total = int(ram.get("totalBytes") or 0)
        used = int(ram.get("usedBytes") or 0)
        if total > 0 and used > 0:
            scores.append(used / total)

    if not scores:
        return {"available": False, "reason": "No RAM data in recent snapshots."}

    latest_score = scores[-1]
    high_count = sum(1 for s in scores if s >= RAM_PRESSURE_HIGH)
    sustained = (high_count / len(scores)) >= SUSTAINED_PRESSURE_RATIO if scores else False

    return {
        "available": True,
        "latestScore": round(latest_score, 4),
        "level": _pressure_level(latest_score),
        "sustained": sustained,
        "sustainedRatio": round(high_count / len(scores), 4) if scores else 0.0,
        "snapshotsAnalyzed": len(scores),
        "highPressureCount": high_count,
    }


def _disk_pressure_analysis(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute sustained disk pressure from recent snapshots."""
    scores: list[float] = []
    latest_disk: dict[str, Any] = {}
    for snapshot in snapshots:
        disk = snapshot.get("system", {}).get("disk", {})
        total = int(disk.get("totalBytes") or 0)
        used = int(disk.get("usedBytes") or 0)
        if total > 0 and used > 0:
            scores.append(used / total)
            latest_disk = disk

    if not scores:
        return {"available": False, "reason": "No disk data in recent snapshots."}

    latest_score = scores[-1]
    high_count = sum(1 for s in scores if s >= DISK_PRESSURE_HIGH)
    sustained = (high_count / len(scores)) >= SUSTAINED_PRESSURE_RATIO if scores else False

    return {
        "available": True,
        "latestScore": round(latest_score, 4),
        "level": _disk_pressure_level(latest_score),
        "sustained": sustained,
        "sustainedRatio": round(high_count / len(scores), 4) if scores else 0.0,
        "snapshotsAnalyzed": len(scores),
        "highPressureCount": high_count,
        "freeBytes": int(latest_disk.get("freeBytes") or 0),
        "totalBytes": int(latest_disk.get("totalBytes") or 0),
    }


def _process_pressure_analysis(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Identify consistently high-memory processes / applications."""
    if not snapshots:
        return {"available": False, "reason": "No snapshots provided."}

    latest = snapshots[-1]
    ram = latest.get("system", {}).get("ram", {})
    total_ram = int(ram.get("totalBytes") or 0)

    top_apps: list[dict[str, Any]] = []
    for app in latest.get("derived", {}).get("applications", [])[:TOP_PROCESS_CONTRIBUTORS]:
        mem = int(app.get("totalMemoryBytes") or 0)
        ram_ratio = round(mem / total_ram, 4) if total_ram > 0 else 0.0
        top_apps.append(
            {
                "application": app.get("application"),
                "totalMemoryBytes": mem,
                "processCount": app.get("processCount"),
                "ramRatio": ram_ratio,
            }
        )

    return {
        "available": True,
        "topContributors": top_apps,
    }


def _overall_level(ram_level: str, disk_level: str) -> str:
    """Derive overall system pressure from component levels."""
    priority = {"critical": 4, "high": 3, "moderate": 2, "low": 1, "unknown": 0}
    levels = [ram_level, disk_level]
    return max(levels, key=lambda x: priority.get(x, 0))


def compute_live_pressure(
    snapshots: list[dict[str, Any]],
    window: int = PRESSURE_WINDOW_SIZE,
) -> dict[str, Any]:
    """Compute current live pressure state from recent snapshots.

    Uses the most recent `window` snapshots. Pressure is only
    declared sustained if it persists across the majority of the window.

    Returns:
        {
            overall: "low" | "moderate" | "high" | "critical",
            ram: { level, sustained, latestScore, ... },
            disk: { level, sustained, latestScore, ... },
            processes: { topContributors: [...] },
            snapshotWindowSize: int,
        }
    """
    def _ts(s: dict[str, Any]) -> datetime:
        raw = s.get("timestamp", "")
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return datetime.min

    ordered = sorted(snapshots, key=_ts)
    window_snapshots = ordered[-window:]

    ram_analysis = _ram_pressure_analysis(window_snapshots)
    disk_analysis = _disk_pressure_analysis(window_snapshots)
    process_analysis = _process_pressure_analysis(window_snapshots)

    ram_level = ram_analysis.get("level", "unknown") if ram_analysis.get("available") else "unknown"
    disk_level = disk_analysis.get("level", "unknown") if disk_analysis.get("available") else "unknown"
    overall = _overall_level(ram_level, disk_level)

    return {
        "overall": overall,
        "ram": ram_analysis,
        "disk": disk_analysis,
        "processes": process_analysis,
        "snapshotWindowSize": len(window_snapshots),
        "totalSnapshotsAvailable": len(snapshots),
    }
