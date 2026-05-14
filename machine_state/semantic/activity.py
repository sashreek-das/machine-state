"""Semantic user activity patterns.

Derives behavioral understanding from accumulated snapshot history:
- peak usage hours (when is the machine busiest?)
- dominant applications (what does the user rely on most?)
- system behavior classification (multitasking vs focused vs light)
- pressure pattern (is pressure consistent or spiky?)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..constants import MB, GB, RAM_PRESSURE_HIGH


def _parse_hour(ts: str | None) -> int | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).hour
    except ValueError:
        return None


def _ordered(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(snapshots, key=lambda s: s.get("timestamp", ""))


# ── Activity builders ─────────────────────────────────────────────────────────

def compute_peak_hours(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identify hours of the day when system load is highest."""
    hour_loads: dict[int, list[float]] = {}
    for snap in snapshots:
        ts = snap.get("timestamp", "")
        hour = _parse_hour(ts)
        if hour is None:
            continue
        score = snap.get("derived", {}).get("metrics", {}).get("systemLoadScore")
        if score is not None:
            hour_loads.setdefault(hour, []).append(float(score))

    result: list[dict[str, Any]] = []
    for hour, scores in sorted(hour_loads.items()):
        avg = sum(scores) / len(scores)
        result.append(
            {
                "hour": hour,
                "label": f"{hour:02d}:00",
                "averageLoadScore": round(avg, 4),
                "sampleCount": len(scores),
            }
        )

    result.sort(key=lambda h: -h["averageLoadScore"])
    return result


def compute_dominant_applications(
    snapshots: list[dict[str, Any]],
    top_n: int = 5,
) -> list[dict[str, Any]]:
    """Identify applications most consistently present and memory-heavy."""
    app_data: dict[str, dict[str, Any]] = {}
    total_snapshots = len(snapshots)

    for snap in snapshots:
        for app in snap.get("derived", {}).get("applications", []):
            name = str(app.get("application", ""))
            mem = int(app.get("totalMemoryBytes") or 0)
            rec = app_data.setdefault(
                name,
                {"application": name, "appearances": 0, "totalMemoryBytes": 0, "peakMemoryBytes": 0},
            )
            rec["appearances"] += 1
            rec["totalMemoryBytes"] += mem
            rec["peakMemoryBytes"] = max(rec["peakMemoryBytes"], mem)

    results: list[dict[str, Any]] = []
    for name, rec in app_data.items():
        count = rec["appearances"]
        avg = int(rec["totalMemoryBytes"] / count) if count > 0 else 0
        results.append(
            {
                "application": name,
                "presenceRatio": round(count / total_snapshots, 4) if total_snapshots > 0 else 0.0,
                "averageMemoryGB": round(avg / GB, 3),
                "peakMemoryGB": round(rec["peakMemoryBytes"] / GB, 3),
                "appearanceCount": count,
            }
        )

    # Sort by a combined score: presence * average memory
    results.sort(
        key=lambda r: -(r["presenceRatio"] * r["averageMemoryGB"]),
    )
    return results[:top_n]


def classify_system_behavior(snapshots: list[dict[str, Any]]) -> str:
    """Classify the general system behavior pattern.

    Returns one of:
    - "heavy_multitasking": many high-memory apps running simultaneously
    - "single_app_focus": one dominant app using most memory
    - "developer_workload": development tools dominate
    - "light_use": low overall pressure
    """
    if not snapshots:
        return "unknown"

    latest = _ordered(snapshots)[-1]
    apps = latest.get("derived", {}).get("applications", [])
    ram = latest.get("system", {}).get("ram", {})
    total_ram = int(ram.get("totalBytes") or 0)

    if not apps or total_ram == 0:
        return "unknown"

    # Count apps above moderate threshold (100 MB)
    heavy_apps = [a for a in apps if int(a.get("totalMemoryBytes") or 0) >= 100 * MB]
    top_mem = int(apps[0].get("totalMemoryBytes") or 0) if apps else 0
    total_app_mem = sum(int(a.get("totalMemoryBytes") or 0) for a in apps)

    # Check for developer tools
    dev_keywords = {"windsurf", "cursor", "vscode", "xcode", "android studio", "docker",
                    "gopls", "node", "python", "java", "codex", "claude"}
    dev_apps = [
        a for a in apps
        if any(kw in str(a.get("application", "")).lower() for kw in dev_keywords)
    ]
    dev_mem = sum(int(a.get("totalMemoryBytes") or 0) for a in dev_apps)
    dev_ratio = dev_mem / total_app_mem if total_app_mem > 0 else 0.0

    pressure_score = float(latest.get("derived", {}).get("metrics", {}).get("systemLoadScore") or 0.0)

    if pressure_score < 0.4:
        return "light_use"
    if dev_ratio >= 0.6:
        return "developer_workload"
    if len(heavy_apps) >= 4:
        return "heavy_multitasking"
    if total_ram > 0 and top_mem / total_ram >= 0.4:
        return "single_app_focus"
    return "heavy_multitasking"


def classify_pressure_pattern(snapshots: list[dict[str, Any]]) -> str:
    """Classify whether system pressure is consistent, spiky, or healthy.

    Returns one of:
    - "consistently_high": pressure is high across most snapshots
    - "spiky": pressure alternates between high and low
    - "healthy": pressure is generally low
    """
    if len(snapshots) < 3:
        return "insufficient_data"

    scores = [
        float(s.get("derived", {}).get("metrics", {}).get("systemLoadScore") or 0.0)
        for s in snapshots
    ]
    scores = [s for s in scores if s > 0]
    if not scores:
        return "insufficient_data"

    avg = sum(scores) / len(scores)
    high_count = sum(1 for s in scores if s >= RAM_PRESSURE_HIGH)
    high_ratio = high_count / len(scores)

    # Measure variance: if scores swing widely, it's spiky
    mean = avg
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    std_dev = variance ** 0.5

    if high_ratio >= RAM_PRESSURE_HIGH:
        return "consistently_high"
    if std_dev >= 0.10 and high_ratio >= 0.25:
        return "spiky"
    return "healthy"


def build_activity_pattern(
    snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a complete semantic activity pattern from snapshot history."""
    if not snapshots:
        return {"available": False, "reason": "No snapshot history available."}

    peak_hours = compute_peak_hours(snapshots)
    dominant_apps = compute_dominant_applications(snapshots)
    behavior = classify_system_behavior(snapshots)
    pressure_pattern = classify_pressure_pattern(snapshots)

    top_peak_hours = [h["label"] for h in peak_hours[:3]]

    _BEHAVIOR_LABELS = {
        "heavy_multitasking": "Heavy Multitasking — multiple resource-intensive apps running simultaneously.",
        "single_app_focus": "Single-App Focus — one dominant application consuming most resources.",
        "developer_workload": "Developer Workload — development tools and build processes are dominant.",
        "light_use": "Light Use — system is running with minimal load.",
        "unknown": "Unknown — insufficient data to classify.",
    }

    _PATTERN_LABELS = {
        "consistently_high": "Consistently High — pressure is elevated across most observed periods.",
        "spiky": "Spiky — pressure alternates between high and low periods.",
        "healthy": "Healthy — pressure is generally within normal bounds.",
        "insufficient_data": "Insufficient data for pattern analysis.",
    }

    return {
        "available": True,
        "snapshotsAnalyzed": len(snapshots),
        "systemBehavior": behavior,
        "systemBehaviorLabel": _BEHAVIOR_LABELS.get(behavior, behavior),
        "pressurePattern": pressure_pattern,
        "pressurePatternLabel": _PATTERN_LABELS.get(pressure_pattern, pressure_pattern),
        "peakHours": peak_hours[:5],
        "topPeakHours": top_peak_hours,
        "dominantApplications": dominant_apps,
    }
