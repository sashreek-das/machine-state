"""Machine capability reasoning.

Deterministically answers questions like:
- Can I install X GB on this machine?
- Can my system handle a heavy app right now?
- What is this machine currently capable of?
- How much will remain after this install?

All reasoning is rule-based, evidence-backed, and reproducible.
"""

from __future__ import annotations

from typing import Any

from ..constants import (
    MB,
    GB,
    INSTALL_SAFE_BUFFER_BYTES,
    LARGE_INSTALL_THRESHOLD_BYTES,
    RAM_HEAVY_APP_FREE_MIN_BYTES,
    RAM_MODERATE_APP_FREE_MIN_BYTES,
)

# Well-known application size estimates (bytes) for capability queries

#Sashreek's ideas: instead of hardcoding this in future scope we will use llm to fetch the sizes so we dont need to maintain this dictionary
KNOWN_APP_SIZES: dict[str, int] = {
    "xcode": 35 * GB,
    "android studio": 8 * GB,
    "unity": 10 * GB,
    "unreal engine": 20 * GB,
    "photoshop": 4 * GB,
    "final cut pro": 3 * GB,
    "logic pro": 1 * GB,
    "vscode": 500 * MB,
    "windsurf": 500 * MB,
    "cursor": 500 * MB,
    "docker": 2 * GB,
    "steam": 1 * GB,
}


def _fmt_gb(b: int) -> float:
    return round(b / GB, 2)


def can_install(
    snapshot: dict[str, Any],
    required_bytes: int,
    app_name: str | None = None,
) -> dict[str, Any]:
    """Determine if an installation is feasible given current disk state.

    Args:
        snapshot: Latest machine snapshot.
        required_bytes: Space required by the installation.
        app_name: Optional app name for known-size lookup.

    Returns:
        Feasibility assessment with recommendation.
    """
    # Resolve size from known apps if not provided
    if required_bytes <= 0 and app_name:
        required_bytes = KNOWN_APP_SIZES.get(app_name.lower().strip(), 0)

    disk = snapshot.get("system", {}).get("disk", {})
    free_bytes = int(disk.get("freeBytes") or 0)
    total_bytes = int(disk.get("totalBytes") or 0)

    if free_bytes <= 0:
        return {
            "feasible": False,
            "reason": "Disk information is unavailable.",
            "requiredGB": _fmt_gb(required_bytes),
            "freeGB": None,
        }

    remaining_after = free_bytes - required_bytes
    has_safe_buffer = remaining_after >= INSTALL_SAFE_BUFFER_BYTES
    feasible = remaining_after > 0

    if not feasible:
        recommendation = (
            f"Insufficient space. Need {_fmt_gb(required_bytes)} GB but only "
            f"{_fmt_gb(free_bytes)} GB is available."
        )
    elif not has_safe_buffer:
        recommendation = (
            f"Possible but tight. Only {_fmt_gb(remaining_after)} GB would remain — "
            f"less than the recommended 5 GB buffer."
        )
    else:
        recommendation = (
            f"Safe to install. {_fmt_gb(remaining_after)} GB will remain after installation."
        )

    return {
        "feasible": feasible,
        "hasSafeBuffer": has_safe_buffer,
        "requiredGB": _fmt_gb(required_bytes),
        "freeGB": _fmt_gb(free_bytes),
        "remainingAfterInstallGB": _fmt_gb(remaining_after),
        "recommendation": recommendation,
        "totalGB": _fmt_gb(total_bytes),
        "appName": app_name,
    }


def ram_capability(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Assess current RAM capability for running additional workloads."""
    ram = snapshot.get("system", {}).get("ram", {})
    available_bytes = int(ram.get("availableBytes") or 0)
    total_bytes = int(ram.get("totalBytes") or 0)
    used_bytes = int(ram.get("usedBytes") or 0)

    if total_bytes <= 0:
        return {"available": False, "reason": "RAM data unavailable."}

    can_run_heavy = available_bytes >= RAM_HEAVY_APP_FREE_MIN_BYTES
    can_run_moderate = available_bytes >= RAM_MODERATE_APP_FREE_MIN_BYTES
    pressure_ratio = used_bytes / total_bytes if total_bytes > 0 else 0.0

    return {
        "available": True,
        "totalGB": _fmt_gb(total_bytes),
        "usedGB": _fmt_gb(used_bytes),
        "availableGB": _fmt_gb(available_bytes),
        "pressureRatio": round(pressure_ratio, 4),
        "canRunHeavyApp": can_run_heavy,
        "canRunModerateApp": can_run_moderate,
        "recommendation": (
            "RAM is healthy — can handle additional workloads." if can_run_moderate
            else "RAM is constrained — close applications before launching heavy ones."
        ),
    }


def system_capability_summary(
    snapshot: dict[str, Any],
    pressure_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarize the full operational capability of the machine right now.

    Combines disk, RAM, and pressure signals into an actionable capability assessment.
    """
    disk = snapshot.get("system", {}).get("disk", {})
    free_bytes = int(disk.get("freeBytes") or 0)
    total_bytes = int(disk.get("totalBytes") or 0)
    used_bytes = int(disk.get("usedBytes") or 0)

    ram_cap = ram_capability(snapshot)
    disk_percent_used = round(used_bytes / total_bytes * 100, 1) if total_bytes > 0 else 0.0

    # Disk capability thresholds
    safe_for_large_install = free_bytes >= LARGE_INSTALL_THRESHOLD_BYTES
    safe_for_small_install = free_bytes >= INSTALL_SAFE_BUFFER_BYTES

    overall_healthy = (
        ram_cap.get("canRunModerateApp", False)
        and safe_for_small_install
        and disk_percent_used < 90
    )

    # Build capability flags
    capabilities: dict[str, bool] = {
        "canRunHeavyApp": ram_cap.get("canRunHeavyApp", False),
        "canRunModerateApp": ram_cap.get("canRunModerateApp", False),
        "canInstallLargeApp": safe_for_large_install,
        "canInstallSmallApp": safe_for_small_install,
        "systemHealthy": overall_healthy,
    }

    # Recommendations
    recommendations: list[str] = []
    if not ram_cap.get("canRunModerateApp", True):
        recommendations.append("Close heavy applications to free RAM.")
    if not safe_for_large_install:
        recommendations.append("Free up disk space before installing large applications.")
    if disk_percent_used >= 90:
        recommendations.append("Disk is above 90% — clear caches and Downloads.")
    if not recommendations:
        recommendations.append("System is in good health.")

    return {
        "capabilities": capabilities,
        "disk": {
            "freeGB": _fmt_gb(free_bytes),
            "usedGB": _fmt_gb(used_bytes),
            "totalGB": _fmt_gb(total_bytes),
            "percentUsed": disk_percent_used,
            "status": "critical" if disk_percent_used >= 90 else (
                "low" if disk_percent_used >= 80 else "healthy"
            ),
        },
        "ram": ram_cap,
        "recommendations": recommendations,
        "overallHealthy": overall_healthy,
    }
