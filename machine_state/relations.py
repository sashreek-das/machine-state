"""Deterministic relationship modeling across machine entities.

Phase 4 extends this module with temporal relationship evolution:
- relationship strength over time (recurrence frequency)
- temporal correlations between entities and pressure events
- causal weight derived from snapshot history
"""

from __future__ import annotations

from typing import Any

from .constants import RAM_PRESSURE_HIGH


def build_relationships(snapshot: dict[str, Any], entities: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    relationships: list[dict[str, Any]] = []
    metrics = snapshot.get("derived", {}).get("metrics", {})

    for application in entities.get("applications", []):
        for process_entity_id in application.get("processEntityIds", []):
            relationships.append(
                {
                    "from": application["entityId"],
                    "to": process_entity_id,
                    "type": "application_contains_process",
                    "evidence": {
                        "totalMemoryBytes": application.get("totalMemoryBytes"),
                    },
                }
            )

        memory_pressure = metrics.get("memoryPressureScore")
        if memory_pressure is not None:
            relationships.append(
                {
                    "from": application["entityId"],
                    "to": "metric:memoryPressure",
                    "type": "application_contributes_to_memory_pressure",
                    "evidence": {
                        "applicationMemoryBytes": application.get("totalMemoryBytes"),
                        "memoryPressureScore": memory_pressure,
                    },
                }
            )

    for project in entities.get("projects", []):
        for folder_entity_id in project.get("folderEntityIds", []):
            relationships.append(
                {
                    "from": project["entityId"],
                    "to": folder_entity_id,
                    "type": "project_contains_folder",
                    "evidence": {
                        "projectSizeBytes": project.get("sizeBytes"),
                    },
                }
            )

    return {
        "relationships": relationships,
        "counts": {
            "applications": len(entities.get("applications", [])),
            "projects": len(entities.get("projects", [])),
            "folders": len(entities.get("folders", [])),
            "processes": len(entities.get("processes", [])),
            "relationships": len(relationships),
        },
    }


# ── Temporal relationship evolution (Phase 4) ─────────────────────────────────

def build_temporal_relationships(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute temporal relationship strength from a series of snapshots.

    Measures:
    - How frequently each application appears during high RAM pressure
    - Recurrence: how often each application-pressure pair co-occurs
    - Causal weight: application memory as fraction of total pressure

    All computations are deterministic, rule-based, and reproducible.
    """
    app_pressure_cooccurrence: dict[str, dict[str, Any]] = {}
    total_high_pressure_snapshots = 0

    for snapshot in snapshots:
        metrics = snapshot.get("derived", {}).get("metrics", {})
        pressure = metrics.get("memoryPressureScore")
        if pressure is None or pressure < RAM_PRESSURE_HIGH:
            continue

        total_high_pressure_snapshots += 1
        total_ram = int(snapshot.get("system", {}).get("ram", {}).get("totalBytes") or 0)

        for app in snapshot.get("derived", {}).get("applications", []):
            name = str(app.get("application", ""))
            mem = int(app.get("totalMemoryBytes") or 0)
            entity_id = f"application:{name.strip().lower()}"
            record = app_pressure_cooccurrence.setdefault(
                entity_id,
                {
                    "entity_id": entity_id,
                    "application": name,
                    "cooccurrenceCount": 0,
                    "totalMemoryDuringPressureBytes": 0,
                    "totalRamDuringPressureBytes": 0,
                },
            )
            record["cooccurrenceCount"] += 1
            record["totalMemoryDuringPressureBytes"] += mem
            record["totalRamDuringPressureBytes"] += total_ram

    temporal_relationships: list[dict[str, Any]] = []
    for entity_id, record in app_pressure_cooccurrence.items():
        count = record["cooccurrenceCount"]
        total_mem = record["totalMemoryDuringPressureBytes"]
        total_ram_sum = record["totalRamDuringPressureBytes"]

        recurrence_frequency = (
            round(count / total_high_pressure_snapshots, 4)
            if total_high_pressure_snapshots > 0
            else 0.0
        )
        causal_weight = (
            round(total_mem / total_ram_sum, 4)
            if total_ram_sum > 0
            else 0.0
        )
        strength = round((recurrence_frequency + causal_weight) / 2.0, 4)

        temporal_relationships.append(
            {
                "from": entity_id,
                "to": "metric:memoryPressure",
                "type": "application_correlates_with_memory_pressure",
                "strength": strength,
                "recurrenceFrequency": recurrence_frequency,
                "causalWeight": causal_weight,
                "cooccurrenceCount": count,
                "totalHighPressureSnapshots": total_high_pressure_snapshots,
                "evidence": {
                    "application": record["application"],
                    "averageMemoryDuringPressureBytes": (
                        int(total_mem / count) if count > 0 else 0
                    ),
                },
            }
        )

    temporal_relationships.sort(key=lambda r: (-r["strength"], r["from"]))

    return {
        "temporalRelationships": temporal_relationships,
        "totalHighPressureSnapshots": total_high_pressure_snapshots,
        "totalSnapshotsAnalyzed": len(snapshots),
        "counts": {
            "temporalRelationships": len(temporal_relationships),
        },
    }
