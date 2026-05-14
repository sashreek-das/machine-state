"""Workload pattern analysis and trajectory classification.

Classifies system trajectory (stable/expanding/contracting) and identifies
recurring time windows where the machine experiences high load.
"""

from __future__ import annotations

from typing import Any

from .. import timeline
from ..constants import (
    GB,
    WORKLOAD_ELEVATED_PRESSURE,
    WORKLOAD_HIGH_PRESSURE,
    WORKLOAD_CRITICAL_PRESSURE,
    RAM_PRESSURE_MODERATE,
)


def _pressure_label(ratio: float) -> str:
    if ratio >= WORKLOAD_CRITICAL_PRESSURE:
        return "Critical"
    if ratio >= WORKLOAD_HIGH_PRESSURE:
        return "High"
    if ratio >= WORKLOAD_ELEVATED_PRESSURE:
        return "Elevated"
    if ratio >= RAM_PRESSURE_MODERATE:
        return "Moderate"
    return "Low"


def classify_workload_trajectory(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify the overall system workload trajectory from trends."""
    ram_trend = timeline.ram_usage_trend(snapshots)
    disk_trend = timeline.disk_usage_trend(snapshots)

    ram_dir = ram_trend.get("direction", "flat") if ram_trend.get("available") else "unknown"
    disk_dir = disk_trend.get("direction", "flat") if disk_trend.get("available") else "unknown"

    if ram_dir == "increasing" and disk_dir == "increasing":
        trajectory, description, risk = "expanding", "Both RAM and disk usage are growing steadily.", "medium"
    elif ram_dir == "increasing":
        trajectory, description, risk = "memory-pressure", "RAM usage is growing. Disk usage is stable.", "medium"
    elif disk_dir == "increasing":
        trajectory, description, risk = "storage-growth", "Disk usage is growing. RAM usage is stable.", "low"
    elif ram_dir == "decreasing" and disk_dir == "decreasing":
        trajectory, description, risk = "contracting", "Both RAM and disk usage are decreasing — system is releasing resources.", "low"
    else:
        trajectory, description, risk = "stable", "System resource usage is stable.", "low"

    ram_rate = ram_trend.get("rateBytesPerHour") if ram_trend.get("available") else None
    disk_rate = disk_trend.get("rateBytesPerHour") if disk_trend.get("available") else None

    return {
        "available": True,
        "trajectory": trajectory,
        "description": description,
        "risk": risk,
        "ramDirection": ram_dir,
        "diskDirection": disk_dir,
        "ramRateGBPerDay": round(ram_rate * 24 / GB, 3) if ram_rate else None,
        "diskRateGBPerDay": round(disk_rate * 24 / GB, 3) if disk_rate else None,
    }


def identify_slowdown_windows(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Find recurring hours of day when the system is typically under high RAM pressure."""
    hour_data: dict[int, list[float]] = {}
    for snap in snapshots:
        ts = snap.get("timestamp")
        dt = timeline._parse_timestamp(ts)
        if dt is None:
            continue
        ram = snap.get("system", {}).get("ram", {})
        total = int(ram.get("totalBytes", 0) or 0)
        used = int(ram.get("usedBytes", 0) or 0)
        if total <= 0:
            continue
        hour_data.setdefault(dt.hour, []).append(used / total)

    if not hour_data:
        return {"available": False, "reason": "No timestamped data available."}

    windows = []
    for hour, pressures in sorted(hour_data.items()):
        avg = sum(pressures) / len(pressures)
        windows.append({
            "hour": hour,
            "avgPressureRatio": round(avg, 3),
            "sampleCount": len(pressures),
            "label": _pressure_label(avg),
        })

    slowdown_windows = [w for w in windows if w["avgPressureRatio"] >= WORKLOAD_ELEVATED_PRESSURE]
    slowdown_windows.sort(key=lambda x: -x["avgPressureRatio"])

    return {
        "available": True,
        "slowdownWindows": slowdown_windows[:5],
        "allWindows": windows,
        "totalObservations": sum(len(p) for p in hour_data.values()),
    }


def get_workload_risk_summary(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize overall workload risk from trajectory and recurring pressure patterns."""
    trajectory = classify_workload_trajectory(snapshots)
    windows = identify_slowdown_windows(snapshots)

    risk_factors: list[str] = []
    risk_score = 0

    traj = trajectory.get("trajectory", "stable")
    if traj == "expanding":
        risk_score += 30
        risk_factors.append("Both RAM and disk usage are growing")
    elif traj == "memory-pressure":
        risk_score += 25
        risk_factors.append("RAM usage is steadily increasing")
    elif traj == "storage-growth":
        risk_score += 15
        risk_factors.append("Disk usage is growing")

    if windows.get("available"):
        high_windows = [w for w in windows.get("slowdownWindows", []) if w["avgPressureRatio"] >= WORKLOAD_HIGH_PRESSURE]
        if len(high_windows) >= 3:
            risk_score += 30
            risk_factors.append(f"High pressure observed during {len(high_windows)} recurring time windows")
        elif len(high_windows) >= 1:
            risk_score += 15
            risk_factors.append(f"Elevated pressure observed during {len(high_windows)} time window(s)")

    risk_level = "High" if risk_score >= 50 else ("Medium" if risk_score >= 25 else "Low")

    return {
        "available": True,
        "riskLevel": risk_level,
        "riskScore": risk_score,
        "riskFactors": risk_factors,
        "trajectory": traj,
        "description": trajectory.get("description", ""),
    }
