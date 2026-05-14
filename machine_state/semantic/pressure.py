"""Semantic pressure states.

Translates raw pressure scores into meaningful, human-readable system states
with explanations and recommendations.

States (ordered by severity):
  healthy           — system is running well
  elevated          — slightly above normal, worth monitoring
  high              — system is under notable pressure
  critical          — system is severely constrained
  sustained_critical — system has been critical for an extended period
"""

from __future__ import annotations

from typing import Any

from ..constants import (
    GB,
    SEMANTIC_RAM_SUSTAINED_CRITICAL,
    SEMANTIC_RAM_CRITICAL,
    SEMANTIC_RAM_HIGH,
    SEMANTIC_RAM_ELEVATED,
    SEMANTIC_DISK_SUSTAINED_CRITICAL,
    SEMANTIC_DISK_CRITICAL,
    SEMANTIC_DISK_HIGH,
    SEMANTIC_DISK_ELEVATED,
)

# ── State definitions ─────────────────────────────────────────────────────────

PRESSURE_STATES: dict[str, dict[str, Any]] = {
    "healthy": {
        "label": "Healthy",
        "scoreRange": (0.0, 0.50),
        "meaning": "System resources are well within comfortable limits.",
        "urgency": "none",
        "color": "green",
    },
    "elevated": {
        "label": "Elevated",
        "scoreRange": (0.50, 0.70),
        "meaning": "Resource usage is above baseline. System is functioning but worth monitoring.",
        "urgency": "low",
        "color": "yellow",
    },
    "high": {
        "label": "High",
        "scoreRange": (0.70, 0.85),
        "meaning": "System is under notable pressure. Performance may be impacted.",
        "urgency": "moderate",
        "color": "orange",
    },
    "critical": {
        "label": "Critical",
        "scoreRange": (0.85, 0.95),
        "meaning": "System is severely resource-constrained. Applications may be slow or unresponsive.",
        "urgency": "high",
        "color": "red",
    },
    "sustained_critical": {
        "label": "Sustained Critical",
        "scoreRange": (0.95, 1.01),
        "meaning": "System has been under critical pressure for an extended period. Immediate action recommended.",
        "urgency": "immediate",
        "color": "dark_red",
    },
}

# RAM-specific recommendations by state
_RAM_RECOMMENDATIONS: dict[str, str] = {
    "healthy": "RAM usage is normal. No action needed.",
    "elevated": "RAM usage is rising. Monitor active applications.",
    "high": "RAM is under pressure. Consider closing unused applications.",
    "critical": "RAM is critically low. Close heavy applications immediately.",
    "sustained_critical": "RAM has been critically low for extended time. Restart applications or reboot.",
}

# Disk-specific recommendations by state
_DISK_RECOMMENDATIONS: dict[str, str] = {
    "healthy": "Disk space is adequate. No action needed.",
    "elevated": "Disk usage is growing. Review Downloads and Caches.",
    "high": "Disk is running low. Clear Caches and Downloads folders.",
    "critical": "Disk is critically low. Free space immediately to avoid system issues.",
    "sustained_critical": "Disk has been critically full. System stability is at risk.",
}

# Disk thresholds — ordered high to low; first match wins.
_DISK_THRESHOLDS: list[tuple[float, str]] = [
    (SEMANTIC_DISK_SUSTAINED_CRITICAL, "sustained_critical"),
    (SEMANTIC_DISK_CRITICAL, "critical"),
    (SEMANTIC_DISK_HIGH, "high"),
    (SEMANTIC_DISK_ELEVATED, "elevated"),
]


def score_to_state(score: float, sustained: bool = False, domain: str = "ram") -> str:
    """Convert a raw pressure score to a semantic state name."""
    if domain == "disk":
        for threshold, state in _DISK_THRESHOLDS:
            if score >= threshold:
                return "sustained_critical" if sustained and state == "critical" else state
        return "healthy"

    # RAM / default
    if score >= SEMANTIC_RAM_SUSTAINED_CRITICAL:
        return "sustained_critical"
    if score >= SEMANTIC_RAM_CRITICAL:
        return "sustained_critical" if sustained else "critical"
    if score >= SEMANTIC_RAM_HIGH:
        return "high"
    if score >= SEMANTIC_RAM_ELEVATED:
        return "elevated"
    return "healthy"


def state_meta(state: str) -> dict[str, Any]:
    """Return metadata for a given pressure state."""
    return PRESSURE_STATES.get(state, PRESSURE_STATES["healthy"])


def build_ram_pressure_semantics(
    ram_data: dict[str, Any],
) -> dict[str, Any]:
    """Build semantic RAM pressure assessment from live pressure engine output."""
    if not ram_data.get("available"):
        return {"available": False, "reason": "No RAM pressure data."}

    score = float(ram_data.get("latestScore") or 0.0)
    sustained = bool(ram_data.get("sustained"))
    state = score_to_state(score, sustained, domain="ram")
    meta = state_meta(state)

    return {
        "available": True,
        "state": state,
        "label": meta["label"],
        "score": score,
        "scorePercent": round(score * 100, 1),
        "sustained": sustained,
        "sustainedRatio": ram_data.get("sustainedRatio"),
        "meaning": meta["meaning"],
        "recommendation": _RAM_RECOMMENDATIONS[state],
        "urgency": meta["urgency"],
        "snapshotsAnalyzed": ram_data.get("snapshotsAnalyzed"),
    }


def build_disk_pressure_semantics(
    disk_data: dict[str, Any],
) -> dict[str, Any]:
    """Build semantic disk pressure assessment from live pressure engine output."""
    if not disk_data.get("available"):
        return {"available": False, "reason": "No disk pressure data."}

    score = float(disk_data.get("latestScore") or 0.0)
    sustained = bool(disk_data.get("sustained"))
    state = score_to_state(score, sustained, domain="disk")
    meta = state_meta(state)

    free_bytes = int(disk_data.get("freeBytes") or 0)
    total_bytes = int(disk_data.get("totalBytes") or 0)

    return {
        "available": True,
        "state": state,
        "label": meta["label"],
        "score": score,
        "scorePercent": round(score * 100, 1),
        "sustained": sustained,
        "freeGB": round(free_bytes / GB, 2),
        "totalGB": round(total_bytes / GB, 2),
        "meaning": meta["meaning"],
        "recommendation": _DISK_RECOMMENDATIONS[state],
        "urgency": meta["urgency"],
        "snapshotsAnalyzed": disk_data.get("snapshotsAnalyzed"),
    }


def _overall_state(ram_state: str, disk_state: str) -> str:
    """Return the more severe of the two states."""
    priority = {
        "sustained_critical": 5,
        "critical": 4,
        "high": 3,
        "elevated": 2,
        "healthy": 1,
    }
    states = [ram_state, disk_state]
    return max(states, key=lambda s: priority.get(s, 0))


def build_semantic_pressure_report(
    live_pressure: dict[str, Any],
) -> dict[str, Any]:
    """Build a complete semantic pressure report from live pressure engine output.

    Wraps the raw pressure data in human-readable states, meanings, and recommendations.
    """
    ram_semantics = build_ram_pressure_semantics(live_pressure.get("ram", {}))
    disk_semantics = build_disk_pressure_semantics(live_pressure.get("disk", {}))

    ram_state = ram_semantics.get("state", "healthy")
    disk_state = disk_semantics.get("state", "healthy")
    overall = _overall_state(ram_state, disk_state)
    overall_meta = state_meta(overall)

    # Top contributors from process pressure
    contributors = live_pressure.get("processes", {}).get("topContributors", [])
    top_contributors = [
        {
            "application": c.get("application"),
            "memoryGB": round(int(c.get("totalMemoryBytes") or 0) / GB, 2),
            "ramPercent": round(float(c.get("ramRatio") or 0) * 100, 1),
        }
        for c in contributors[:3]
    ]

    return {
        "overall": {
            "state": overall,
            "label": overall_meta["label"],
            "meaning": overall_meta["meaning"],
            "urgency": overall_meta["urgency"],
        },
        "ram": ram_semantics,
        "disk": disk_semantics,
        "topContributors": top_contributors,
        "snapshotWindowSize": live_pressure.get("snapshotWindowSize"),
    }
