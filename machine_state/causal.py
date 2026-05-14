"""Deterministic causal heuristics for machine behavior."""

from __future__ import annotations

from typing import Any

from . import timeline
from .constants import RAM_PRESSURE_HIGH, DISK_PRESSURE_CRITICAL


def explain_high_ram(snapshot: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = snapshot.get("derived", {}).get("metrics", {})
    memory_pressure = metrics.get("memoryPressureScore")
    top_applications = list(snapshot.get("derived", {}).get("applications", []))[:3]
    app_correlations = timeline.correlate_applications_with_memory_spikes(snapshots, limit=3)

    causes: list[dict[str, Any]] = []
    if memory_pressure is not None and memory_pressure >= RAM_PRESSURE_HIGH:
        causes.append(
            {
                "type": "memory_pressure",
                "summary": f"RAM pressure is elevated at {round(float(memory_pressure) * 100, 2)}%.",
                "evidence": {
                    "memoryPressureScore": memory_pressure,
                },
            }
        )

    for application in top_applications:
        total_memory = int(application.get("totalMemoryBytes", 0) or 0)
        if total_memory <= 0:
            continue
        causes.append(
            {
                "type": "top_application_memory",
                "summary": f"{application.get('application')} is consuming {total_memory} bytes across {application.get('processCount')} processes.",
                "evidence": application,
            }
        )

    for correlation in app_correlations:
        causes.append(
            {
                "type": "historical_memory_growth",
                "summary": f"{correlation.get('application')} repeatedly grew during RAM spikes ({correlation.get('totalApplicationMemoryGrowthBytes')} bytes across {correlation.get('spikeCount')} spikes).",
                "evidence": correlation,
            }
        )

    return {
        "available": bool(causes),
        "causes": causes,
    }


def explain_disk_growth(snapshot: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = snapshot.get("derived", {}).get("metrics", {})
    disk_pressure = metrics.get("diskPressureScore")
    growing = timeline.growing_folders(snapshots, limit=5)
    causes: list[dict[str, Any]] = []

    if disk_pressure is not None and disk_pressure >= DISK_PRESSURE_CRITICAL:
        causes.append(
            {
                "type": "disk_pressure",
                "summary": f"Disk pressure is elevated at {round(float(disk_pressure) * 100, 2)}% used.",
                "evidence": {
                    "diskPressureScore": disk_pressure,
                },
            }
        )

    for folder in growing:
        causes.append(
            {
                "type": "growing_folder",
                "summary": f"{folder.get('name')} grew by {folder.get('deltaBytes')} bytes over the observed window.",
                "evidence": folder,
            }
        )

    return {
        "available": bool(causes),
        "causes": causes,
    }


def explain_system_slowdown(snapshot: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    ram_explanation = explain_high_ram(snapshot, snapshots)
    disk_explanation = explain_disk_growth(snapshot, snapshots)
    causes = list(ram_explanation.get("causes", [])) + list(disk_explanation.get("causes", []))
    return {
        "available": bool(causes),
        "causes": causes,
    }
