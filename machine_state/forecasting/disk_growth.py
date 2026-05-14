"""Disk growth forecasting.

Projects disk exhaustion dates and identifies fastest-growing folders
using observed growth rates from historical snapshots.
"""

from __future__ import annotations

from typing import Any

from .. import forecast as _base
from .. import timeline
from ..constants import GB, DISK_FORECAST_THRESHOLD_PCT

_DAY_HOURS = 24.0


def forecast_disk_exhaustion(
    snapshots: list[dict[str, Any]],
    threshold_percent: float = DISK_FORECAST_THRESHOLD_PCT,
) -> dict[str, Any]:
    """Forecast when disk will reach threshold_percent usage.

    Returns days/hours until threshold and growth rate in GB/day.
    Returns available=False if insufficient history or disk is shrinking.
    """
    result = _base.forecast_disk_pressure(snapshots, percent_threshold=threshold_percent)
    if not result.get("available"):
        return result

    summary = result.get("summary", {})
    hours = result.get("hoursUntilThreshold")
    days = round(hours / _DAY_HOURS, 1) if hours is not None else None

    rate_bytes_per_hour = summary.get("rateBytesPerHour")
    rate_gb_per_day = round(rate_bytes_per_hour * _DAY_HOURS / GB, 3) if rate_bytes_per_hour else None

    return {
        "available": True,
        "alreadyExceeded": result.get("alreadyExceeded", False),
        "thresholdPercent": threshold_percent,
        "daysUntilThreshold": days,
        "hoursUntilThreshold": hours,
        "rateGBPerDay": rate_gb_per_day,
        "direction": summary.get("direction"),
        "path": result.get("path"),
    }


def get_folder_growth_hotspots(
    snapshots: list[dict[str, Any]],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Return the fastest-growing folders with GB/day rates."""
    raw = timeline.growing_folders(snapshots, limit=limit)
    result = []
    for item in raw:
        rate_bytes_per_hour = item.get("rateBytesPerHour") or 0
        rate_gb_per_day = round(rate_bytes_per_hour * _DAY_HOURS / GB, 3) if rate_bytes_per_hour else None
        delta_bytes = int(item.get("deltaBytes", 0) or 0)
        result.append({
            "name": item.get("name"),
            "path": item.get("path"),
            "deltaGB": round(delta_bytes / GB, 3),
            "rateGBPerDay": rate_gb_per_day,
            "startTimestamp": item.get("startTimestamp"),
            "endTimestamp": item.get("endTimestamp"),
        })
    return result


def estimate_disk_growth_rate(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate overall disk growth rate in GB/day from historical trend."""
    trend = timeline.disk_usage_trend(snapshots)
    if not trend.get("available"):
        return {"available": False, "reason": trend.get("reason", "Insufficient history.")}

    rate_bytes_per_hour = trend.get("rateBytesPerHour")
    if rate_bytes_per_hour is None:
        return {"available": False, "reason": "Could not compute growth rate."}

    direction = trend.get("direction", "flat")
    delta_gb = round((int(trend.get("deltaBytes", 0) or 0)) / GB, 3)
    rate_gb_per_day = round(rate_bytes_per_hour * _DAY_HOURS / GB, 3)

    return {
        "available": True,
        "rateGBPerDay": rate_gb_per_day,
        "direction": direction,
        "deltaGB": delta_gb,
        "durationSeconds": trend.get("durationSeconds"),
        "startTimestamp": trend.get("startTimestamp"),
        "endTimestamp": trend.get("endTimestamp"),
    }
