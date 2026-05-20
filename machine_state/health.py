"""Composite machine health score (0–100).

Five weighted components:
  ram    30% — current RAM utilisation
  disk   25% — current disk utilisation
  proc   15% — top process RAM footprint
  event  15% — critical events in the past hour
  fcast  15% — estimated days until disk is full
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .constants import (
    RAM_PRESSURE_HIGH,
    RAM_PRESSURE_CRITICAL,
    DISK_PRESSURE_HIGH,
    DISK_PRESSURE_CRITICAL,
)

_WEIGHTS: dict[str, float] = {
    "ram": 0.30, "disk": 0.25, "proc": 0.15,
    "event": 0.15, "fcast": 0.15,
}

_LABELS: list[tuple[int, str]] = [
    (85, "Healthy"),
    (65, "Elevated"),
    (45, "Degraded"),
    (25, "Under stress"),
    (0,  "Critical"),
]


def _label(score: int) -> str:
    for threshold, name in _LABELS:
        if score >= threshold:
            return name
    return "Critical"


def _ram_component(snapshots: list[dict[str, Any]]) -> int:
    if not snapshots:
        return 50
    ram = snapshots[-1].get("system", {}).get("ram", {})
    total = int(ram.get("totalBytes") or 0)
    used = int(ram.get("usedBytes") or 0)
    if not total:
        return 50
    r = used / total
    if r >= RAM_PRESSURE_CRITICAL:
        return 10
    if r >= RAM_PRESSURE_HIGH:
        return 45
    if r >= 0.50:
        return 75
    return 100


def _disk_component(snapshots: list[dict[str, Any]]) -> int:
    if not snapshots:
        return 50
    disk = snapshots[-1].get("system", {}).get("disk", {})
    total = int(disk.get("totalBytes") or 0)
    used = int(disk.get("usedBytes") or 0)
    if not total:
        return 50
    r = used / total
    if r >= DISK_PRESSURE_CRITICAL:
        return 15
    if r >= DISK_PRESSURE_HIGH:
        return 50
    if r >= 0.65:
        return 80
    return 100


def _proc_component(snapshots: list[dict[str, Any]]) -> int:
    if not snapshots:
        return 50
    latest = snapshots[-1]
    total_ram = int(latest.get("system", {}).get("ram", {}).get("totalBytes") or 0)
    apps = latest.get("derived", {}).get("applications", [])
    if not apps or not total_ram:
        return 80
    top = int(apps[0].get("totalMemoryBytes") or 0)
    r = top / total_ram
    if r >= 0.70:
        return 20
    if r >= 0.50:
        return 50
    if r >= 0.30:
        return 75
    return 100


def _event_component(events: list[dict[str, Any]]) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = critical = 0
    for e in events:
        try:
            ts = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
        except (ValueError, KeyError):
            continue
        if ts >= cutoff:
            recent += 1
            if e.get("severity") == "critical":
                critical += 1
    if critical >= 2:
        return 20
    if critical >= 1:
        return 40
    if recent >= 5:
        return 60
    if recent >= 2:
        return 80
    return 100


def _fcast_component(snapshots: list[dict[str, Any]]) -> int:
    """Linear disk growth projection → score component."""
    if len(snapshots) < 2:
        return 80
    points: list[tuple[datetime, int, int]] = []
    for s in snapshots:
        disk = s.get("system", {}).get("disk", {})
        used = int(disk.get("usedBytes") or 0)
        total = int(disk.get("totalBytes") or 0)
        try:
            ts = datetime.fromisoformat(
                str(s.get("timestamp", "")).replace("Z", "+00:00")
            )
        except ValueError:
            continue
        if used and total:
            points.append((ts, used, total))
    if len(points) < 2:
        return 80
    points.sort(key=lambda p: p[0])
    hours = (points[-1][0] - points[0][0]).total_seconds() / 3600
    if hours < 0.1:
        return 80
    rate = (points[-1][1] - points[0][1]) / hours
    if rate <= 0:
        return 100
    free = points[-1][2] - points[-1][1]
    days = (free / rate) / 24
    if days < 3:
        return 10
    if days < 7:
        return 30
    if days < 15:
        return 55
    if days < 30:
        return 75
    return 100


def compute_health_score(
    snapshots: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return composite health dict: score (0–100), label, components, ts."""
    ram   = _ram_component(snapshots)
    disk  = _disk_component(snapshots)
    proc  = _proc_component(snapshots)
    event = _event_component(events)
    fcast = _fcast_component(snapshots)

    score = int(
        ram   * _WEIGHTS["ram"]
        + disk  * _WEIGHTS["disk"]
        + proc  * _WEIGHTS["proc"]
        + event * _WEIGHTS["event"]
        + fcast * _WEIGHTS["fcast"]
    )

    return {
        "score": score,
        "label": _label(score),
        "components": {
            "ram": ram, "disk": disk, "process": proc,
            "events": event, "forecast": fcast,
        },
        "ts": int(datetime.now(timezone.utc).timestamp()),
    }
