"""RAM pressure trajectory prediction.

Projects RAM saturation from observed growth rates and identifies
recurring high-pressure time windows using historical snapshots.
"""

from __future__ import annotations

from typing import Any

from .. import timeline
from ..constants import GB, RAM_PRESSURE_HIGH, RAM_PRESSURE_CRITICAL

_DAY_HOURS = 24.0


def predict_ram_trajectory(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Predict RAM usage trajectory and time to saturation (95% threshold).

    Returns direction, growth rate, and estimated days until saturation.
    """
    trend = timeline.ram_usage_trend(snapshots)
    if not trend.get("available"):
        return {"available": False, "reason": trend.get("reason", "Insufficient history.")}

    points = trend.get("points", [])
    if not points:
        return {"available": False, "reason": "No RAM data points."}

    last = points[-1]
    used_bytes = int(last.get("usedBytes", 0) or 0)

    # Find total RAM from snapshots
    total_ram = None
    for snap in reversed(snapshots):
        raw = snap.get("system", {}).get("ram", {})
        if raw.get("totalBytes"):
            total_ram = int(raw["totalBytes"])
            break

    rate_per_hour = trend.get("rateBytesPerHour")
    direction = trend.get("direction", "flat")

    hours_to_saturation = None
    if total_ram and rate_per_hour and rate_per_hour > 0:
        threshold = int(total_ram * RAM_PRESSURE_CRITICAL)
        remaining = threshold - used_bytes
        hours_to_saturation = 0.0 if remaining <= 0 else round(remaining / rate_per_hour, 2)

    days_to_saturation = None
    if hours_to_saturation is not None:
        days_to_saturation = round(hours_to_saturation / _DAY_HOURS, 1)

    return {
        "available": True,
        "direction": direction,
        "usedGB": round(used_bytes / GB, 2),
        "totalGB": round(total_ram / GB, 2) if total_ram else None,
        "rateGBPerDay": round(rate_per_hour * _DAY_HOURS / GB, 3) if rate_per_hour else None,
        "hoursToSaturation": hours_to_saturation,
        "daysToSaturation": days_to_saturation,
        "observationCount": len(points),
    }


def simulate_app_launch_impact(
    snapshot: dict[str, Any],
    app_name: str,
    recent_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Simulate RAM impact of launching an app based on its historical average memory usage."""
    trend = timeline.application_memory_trend(recent_snapshots, app_name)

    ram = snapshot.get("system", {}).get("ram", {})
    total_bytes = int(ram.get("totalBytes", 0) or 0)
    available_bytes = int(ram.get("availableBytes", 0) or 0)

    total_gb = round(total_bytes / GB, 2) if total_bytes else None
    available_gb = round(available_bytes / GB, 2) if available_bytes else None

    if not trend.get("available"):
        return {
            "available": False,
            "reason": f"No memory history available for '{app_name}'.",
            "totalGB": total_gb,
            "availableGB": available_gb,
        }

    points = trend.get("points", [])
    if not points:
        return {"available": False, "reason": "No memory data points for this app."}

    avg_mem_bytes = int(sum(int(p.get("totalMemoryBytes", 0) or 0) for p in points) / len(points))
    peak_point = trend.get("peak") or {}
    peak_mem_bytes = int(peak_point.get("totalMemoryBytes", 0) or 0)
    if not peak_mem_bytes:
        peak_mem_bytes = avg_mem_bytes

    remaining_after_avg = available_bytes - avg_mem_bytes
    # "safe" = leaves at least 10% of total RAM free
    safe_floor = int(total_bytes * 0.10) if total_bytes else 0
    can_run_safely = remaining_after_avg > safe_floor

    return {
        "available": True,
        "application": app_name,
        "estimatedMemoryGB": round(avg_mem_bytes / GB, 2),
        "peakMemoryGB": round(peak_mem_bytes / GB, 2),
        "currentAvailableGB": available_gb,
        "remainingAfterLaunchGB": round(remaining_after_avg / GB, 2),
        "canRunSafely": can_run_safely,
        "observationCount": len(points),
    }


def identify_recurring_pressure_windows(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Identify hours of day where RAM pressure consistently runs high."""
    hour_pressure: dict[int, list[float]] = {}
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
        hour_pressure.setdefault(dt.hour, []).append(used / total)

    if not hour_pressure:
        return {"available": False, "reason": "No timestamped RAM data available."}

    high_hours = []
    for hour, ratios in sorted(hour_pressure.items()):
        avg = sum(ratios) / len(ratios)
        if avg >= RAM_PRESSURE_HIGH:
            high_hours.append({
                "hour": hour,
                "avgPressureRatio": round(avg, 3),
                "sampleCount": len(ratios),
            })

    high_hours.sort(key=lambda x: -x["avgPressureRatio"])

    return {
        "available": True,
        "highPressureHours": high_hours[:5],
        "totalHoursAnalyzed": len(hour_pressure),
    }
