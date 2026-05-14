"""Deterministic forecasting over snapshot timelines."""

from __future__ import annotations

from typing import Any

from . import timeline
from .constants import (
    DISK_FORECAST_THRESHOLD_PCT,
    FOLDER_GROWTH_FORECAST_FLOOR_BYTES,
    FOLDER_GROWTH_FORECAST_MULTIPLIER,
)


def _project_threshold_crossing(points: list[dict[str, Any]], value_key: str, target_value: int) -> dict[str, Any]:
    if len(points) < 2:
        return {
            "available": False,
            "reason": "At least two historical points are required for forecasting.",
        }

    summary = timeline._series_summary(points, value_key)
    rate_per_hour = summary.get("rateBytesPerHour")
    if rate_per_hour is None or rate_per_hour <= 0:
        return {
            "available": False,
            "reason": "The observed trend is not increasing, so no forward pressure crossing can be projected.",
            "summary": summary,
        }

    current_value = int(points[-1].get(value_key, 0) or 0)
    remaining = target_value - current_value
    if remaining <= 0:
        return {
            "available": True,
            "alreadyExceeded": True,
            "hoursUntilThreshold": 0.0,
            "summary": summary,
        }

    hours_until_threshold = round(remaining / float(rate_per_hour), 2)
    return {
        "available": True,
        "alreadyExceeded": False,
        "hoursUntilThreshold": hours_until_threshold,
        "summary": summary,
    }


def forecast_disk_pressure(snapshots: list[dict[str, Any]], percent_threshold: float = DISK_FORECAST_THRESHOLD_PCT) -> dict[str, Any]:
    trend = timeline.disk_usage_trend(snapshots)
    if not trend.get("available"):
        return trend

    points = list(trend.get("points", []))
    if not points:
        return {
            "available": False,
            "reason": "Disk history is empty.",
        }

    total_bytes = int(points[-1].get("totalBytes", 0) or 0)
    if total_bytes <= 0:
        return {
            "available": False,
            "reason": "Disk total bytes are missing from the latest historical point.",
        }

    threshold_bytes = int((percent_threshold / 100.0) * total_bytes)
    forecast = _project_threshold_crossing(points, "usedBytes", threshold_bytes)
    forecast["thresholdPercent"] = percent_threshold
    forecast["thresholdUsedBytes"] = threshold_bytes
    forecast["path"] = points[-1].get("path")
    return forecast


def forecast_folder_growth(snapshots: list[dict[str, Any]], folder_name: str, target_bytes: int | None = None) -> dict[str, Any]:
    trend = timeline.folder_size_trend(snapshots, folder_name)
    if not trend.get("available"):
        return trend

    points = list(trend.get("points", []))
    if not points:
        return {
            "available": False,
            "reason": "Folder history is empty.",
        }

    current_size = int(points[-1].get("sizeBytes", 0) or 0)
    threshold_bytes = target_bytes if target_bytes is not None else max(
        int(current_size * FOLDER_GROWTH_FORECAST_MULTIPLIER),
        current_size + FOLDER_GROWTH_FORECAST_FLOOR_BYTES,
    )
    forecast = _project_threshold_crossing(points, "sizeBytes", threshold_bytes)
    forecast["folder"] = folder_name
    forecast["thresholdBytes"] = threshold_bytes
    forecast["currentSizeBytes"] = current_size
    return forecast
