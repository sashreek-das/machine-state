"""Application memory trends and overall risk scoring.

Aggregates per-app memory trends, computes a machine risk score,
and generates proactive operational insights.
"""

from __future__ import annotations

from typing import Any

from .. import timeline
from ..constants import (
    GB,
    DISK_PRESSURE_MODERATE,
    TREND_RAM_ELEVATED,
    TREND_RAM_HIGH,
    TREND_RAM_CRITICAL,
    TREND_DISK_HIGH,
    TREND_DISK_CRITICAL,
    RAM_DELTA_WARNING_BYTES,
    TREND_RAPID_GROWTH_BYTES_PER_HOUR,
)

_LOW_DISK_THRESHOLD = 1.0 - TREND_DISK_HIGH   # free fraction below which disk is "low"
_DISK_GROWTH_WARNING_GB = 1.0                  # flag if disk growing > 1 GB/day


def _trend_label(direction: str, rate_bytes_per_hour: float | None) -> str:
    if direction == "increasing":
        if rate_bytes_per_hour and rate_bytes_per_hour > TREND_RAPID_GROWTH_BYTES_PER_HOUR:
            return "Rapidly Growing"
        return "Growing"
    if direction == "decreasing":
        return "Shrinking"
    return "Stable"


def get_app_memory_trends(
    snapshots: list[dict[str, Any]],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Return per-application memory trends ranked by growth and average usage."""
    app_names: set[str] = set()
    for snap in snapshots:
        for app in snap.get("derived", {}).get("applications", []):
            name = app.get("application")
            if name:
                app_names.add(name)

    trends = []
    for name in app_names:
        trend = timeline.application_memory_trend(snapshots, name)
        if not trend.get("available"):
            continue
        points = trend.get("points", [])
        if not points:
            continue

        rate = trend.get("rateBytesPerHour")
        direction = trend.get("direction", "flat")
        avg_bytes = sum(int(p.get("totalMemoryBytes", 0) or 0) for p in points) / len(points)
        peak = trend.get("peak") or {}
        peak_bytes = int(peak.get("totalMemoryBytes", 0) or 0)

        trends.append({
            "application": name,
            "direction": direction,
            "averageGB": round(avg_bytes / GB,2),
            "peakGB": round(peak_bytes / GB,2),
            "rateGBPerDay": round(rate * 24 / GB,4) if rate else None,
            "observationCount": len(points),
            "trend": _trend_label(direction, rate),
        })

    # Increasing first, then by average memory desc
    trends.sort(key=lambda x: (0 if x["direction"] == "increasing" else 1, -x["averageGB"]))
    return trends[:top_n]


def compute_overall_risk_score(
    snapshot: dict[str, Any],
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute a 0–100 risk score for the current machine state."""
    risk_score = 0
    factors: list[str] = []

    # Current RAM
    ram = snapshot.get("system", {}).get("ram", {})
    total_ram = int(ram.get("totalBytes", 0) or 0)
    used_ram = int(ram.get("usedBytes", 0) or 0)
    if total_ram > 0:
        ram_ratio = used_ram / total_ram
        if ram_ratio >= TREND_RAM_CRITICAL:
            risk_score += 35
            factors.append(f"RAM at {round(ram_ratio * 100, 1)}% — Critical")
        elif ram_ratio >= TREND_RAM_HIGH:
            risk_score += 25
            factors.append(f"RAM at {round(ram_ratio * 100, 1)}% — High")
        elif ram_ratio >= TREND_RAM_ELEVATED:
            risk_score += 15
            factors.append(f"RAM at {round(ram_ratio * 100, 1)}% — Elevated")

    # Current disk
    disk = snapshot.get("system", {}).get("disk", {})
    total_disk = int(disk.get("totalBytes", 0) or 0)
    used_disk = int(disk.get("usedBytes", 0) or 0)
    if total_disk > 0:
        disk_ratio = used_disk / total_disk
        if disk_ratio >= TREND_DISK_CRITICAL:
            risk_score += 35
            factors.append(f"Disk at {round(disk_ratio * 100, 1)}% — Critical")
        elif disk_ratio >= TREND_DISK_HIGH:
            risk_score += 20
            factors.append(f"Disk at {round(disk_ratio * 100, 1)}% — High")
        elif disk_ratio >= DISK_PRESSURE_MODERATE:
            risk_score += 10
            factors.append(f"Disk at {round(disk_ratio * 100, 1)}% — Elevated")

    # Historical trends
    if len(snapshots) >= 2:
        ram_trend = timeline.ram_usage_trend(snapshots)
        if ram_trend.get("available") and ram_trend.get("direction") == "increasing":
            risk_score += 10
            factors.append("RAM usage trending upward")

        disk_trend = timeline.disk_usage_trend(snapshots)
        if disk_trend.get("available") and disk_trend.get("direction") == "increasing":
            risk_score += 10
            factors.append("Disk usage trending upward")

    risk_score = min(100, risk_score)
    risk_level = "High" if risk_score >= 70 else ("Medium" if risk_score >= 40 else "Low")

    return {
        "available": True,
        "riskScore": risk_score,
        "riskLevel": risk_level,
        "riskFactors": factors,
        "snapshotCount": len(snapshots),
    }


def get_proactive_insights(
    snapshot: dict[str, Any],
    snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate prioritized, actionable insights from current state and trends."""
    insights: list[dict[str, Any]] = []

    # Disk growth warning
    if len(snapshots) >= 2:
        disk_trend = timeline.disk_usage_trend(snapshots)
        if disk_trend.get("available") and disk_trend.get("direction") == "increasing":
            rate = disk_trend.get("rateBytesPerHour", 0) or 0
            rate_gb_day = rate * 24 / GB
            if rate_gb_day > _DISK_GROWTH_WARNING_GB:
                insights.append({
                    "type": "disk_growth",
                    "severity": "warning",
                    "message": f"Disk is growing at {round(rate_gb_day, 2)} GB/day — monitor usage closely.",
                    "action": "Run storage cleanup analysis to identify what is growing.",
                })

    # RAM trend
    if len(snapshots) >= 2:
        ram_trend = timeline.ram_usage_trend(snapshots)
        if ram_trend.get("available") and ram_trend.get("direction") == "increasing":
            delta = int(ram_trend.get("deltaBytes", 0) or 0)
            if delta > RAM_DELTA_WARNING_BYTES:
                insights.append({
                    "type": "ram_growth",
                    "severity": "info",
                    "message": f"RAM usage has grown by {round(delta / GB, 2)} GB over observed history.",
                    "action": "Check which applications are consuming increasing memory.",
                })

    # Current RAM pressure
    ram = snapshot.get("system", {}).get("ram", {})
    total_ram = int(ram.get("totalBytes", 0) or 0)
    used_ram = int(ram.get("usedBytes", 0) or 0)
    if total_ram > 0 and (used_ram / total_ram) >= TREND_RAM_ELEVATED:
        insights.append({
            "type": "high_ram",
            "severity": "warning",
            "message": f"RAM usage is currently at {round(used_ram / total_ram * 100, 1)}% — system under pressure.",
            "action": "Close unused applications to free memory.",
        })

    # Low disk space
    disk = snapshot.get("system", {}).get("disk", {})
    total_disk = int(disk.get("totalBytes", 0) or 0)
    free_disk = int(disk.get("freeBytes", 0) or 0)
    if total_disk > 0 and free_disk / total_disk < _LOW_DISK_THRESHOLD:
        insights.append({
            "type": "low_disk",
            "severity": "warning",
            "message": (
                f"Only {round(free_disk / GB,1)} GB of disk space remaining "
                f"({round(free_disk / total_disk * 100, 1)}% free)."
            ),
            "action": "Run a storage cleanup to reclaim space.",
        })

    # Fastest-growing folders
    if len(snapshots) >= 2:
        hotspots = timeline.growing_folders(snapshots, limit=3)
        for folder in hotspots:
            delta = int(folder.get("deltaBytes", 0) or 0)
            if delta > GB:
                insights.append({
                    "type": "folder_growth",
                    "severity": "info",
                    "message": f"'{folder.get('name', '?')}' grew by {round(delta / GB,2)} GB.",
                    "action": f"Inspect '{folder.get('path', '?')}' for unnecessary files.",
                })

    # Sort: warnings first, then info
    severity_order = {"warning": 0, "info": 1}
    insights.sort(key=lambda x: severity_order.get(x.get("severity", "info"), 2))
    return insights
