"""Install impact simulation.

Simulates post-install disk state and projects long-term safety
based on current disk space and observed growth rates.
"""

from __future__ import annotations

from typing import Any

from .. import timeline
from ..constants import (
    GB,
    INSTALL_SAFE_BUFFER_BYTES,
    INSTALL_CRITICAL_FREE_PCT,
)

_TIGHT_FREE_PCT = 10.0    # <10% free = tight
_LONG_TERM_DAYS = 30


def simulate_install_impact(
    snapshot: dict[str, Any],
    required_gb: float,
    snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Simulate disk state after installing a payload of required_gb.

    Optionally uses historical snapshots to project how long the remaining
    space will last at the current growth rate.
    """
    disk = snapshot.get("system", {}).get("disk", {})
    free_bytes = int(disk.get("freeBytes", 0) or 0)
    total_bytes = int(disk.get("totalBytes", 0) or 0)

    required_bytes = int(required_gb * GB)
    remaining_bytes = free_bytes - required_bytes

    if total_bytes > 0:
        remaining_pct = round(remaining_bytes / total_bytes * 100, 1)
        current_free_pct = round(free_bytes / total_bytes * 100, 1)
    else:
        remaining_pct = None
        current_free_pct = None

    feasible = remaining_bytes > 0
    has_safe_buffer = remaining_bytes >= INSTALL_SAFE_BUFFER_BYTES

    if remaining_pct is not None and remaining_pct < INSTALL_CRITICAL_FREE_PCT:
        post_status = "critical"
    elif remaining_pct is not None and remaining_pct < _TIGHT_FREE_PCT:
        post_status = "tight"
    else:
        post_status = "safe"

    if not feasible:
        shortage_gb = round((required_bytes - free_bytes) / GB, 2)
        recommendation = f"Installation not feasible — {shortage_gb} GB short. Free up space first."
    elif not has_safe_buffer:
        recommendation = "Installation is possible but leaves very little free space. Consider cleanup first."
    else:
        recommendation = "Installation is feasible with sufficient space remaining."

    result: dict[str, Any] = {
        "available": True,
        "requiredGB": required_gb,
        "currentFreeGB": round(free_bytes / GB, 2),
        "currentFreePercent": current_free_pct,
        "remainingAfterInstallGB": round(remaining_bytes / GB, 2),
        "remainingAfterInstallPercent": remaining_pct,
        "feasible": feasible,
        "hasSafeBuffer": has_safe_buffer,
        "postInstallStatus": post_status,
        "recommendation": recommendation,
    }

    # Growth-rate projection
    if snapshots and len(snapshots) >= 2 and remaining_bytes > 0:
        trend = timeline.disk_usage_trend(snapshots)
        if trend.get("available"):
            rate = trend.get("rateBytesPerHour")
            if rate and rate > 0:
                hours_to_full = remaining_bytes / rate
                days_to_full = round(hours_to_full / 24, 1)
                result["daysUntilFullAfterInstall"] = days_to_full
                if days_to_full < 7:
                    result["longTermSafe"] = False
                    result["longTermWarning"] = (
                        f"At current growth rate, disk will be full within {days_to_full} days after install."
                    )
                else:
                    result["longTermSafe"] = True
                    if days_to_full < 60:
                        result["longTermWarning"] = (
                            f"Disk may fill up within ~{days_to_full} days at current growth rate."
                        )

    return result


def check_long_term_safety(
    snapshot: dict[str, Any],
    required_gb: float,
    snapshots: list[dict[str, Any]],
    days: int = _LONG_TERM_DAYS,
) -> dict[str, Any]:
    """Check whether disk will remain safe for `days` days after installing required_gb."""
    disk = snapshot.get("system", {}).get("disk", {})
    free_bytes = int(disk.get("freeBytes", 0) or 0)
    total_bytes = int(disk.get("totalBytes", 0) or 0)
    required_bytes = int(required_gb * GB)

    remaining_after_install = free_bytes - required_bytes
    if remaining_after_install <= 0:
        return {
            "available": True,
            "safeFor30Days": False,
            "reason": "Installation not feasible with current free space.",
            "requiredGB": required_gb,
            "freeGB": round(free_bytes / GB, 2),
        }

    trend = timeline.disk_usage_trend(snapshots)
    if not trend.get("available"):
        return {"available": False, "reason": "Insufficient history for long-term projection."}

    rate_per_hour = trend.get("rateBytesPerHour")
    if not rate_per_hour or rate_per_hour <= 0:
        return {
            "available": True,
            "safeFor30Days": True,
            "reason": "Disk is not growing. Space should remain stable.",
            "requiredGB": required_gb,
            "remainingAfterInstallGB": round(remaining_after_install / GB, 2),
        }

    growth_in_period = int(rate_per_hour * 24 * days)
    remaining_after_growth = remaining_after_install - growth_in_period
    min_safe_bytes = int(total_bytes * 0.05) if total_bytes > 0 else INSTALL_SAFE_BUFFER_BYTES
    safe = remaining_after_growth > min_safe_bytes

    return {
        "available": True,
        "safeFor30Days": safe,
        "daysAnalyzed": days,
        "requiredGB": required_gb,
        "remainingAfterInstallGB": round(remaining_after_install / GB, 2),
        "projectedGrowthGB": round(growth_in_period / GB, 2),
        "projectedRemainingGB": round(remaining_after_growth / GB, 2),
        "rateGBPerDay": round(rate_per_hour * 24 / GB, 3),
        "reason": (
            "Sufficient space projected after install and growth." if safe
            else f"At current growth rate, disk may run critically low within {days} days after install."
        ),
    }
