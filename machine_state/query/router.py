"""Thin dispatch coordinator for the query layer.

This module is the single public entry point.  It:
  1. Guards against a missing snapshot.
  2. Runs Phase 5 semantic detection first.
  3. Falls back to domain/operation detection and dispatches to handlers.

No answer-building logic lives here — all of that is in handlers.py.
"""

from __future__ import annotations

from typing import Any

from .handlers import (
    unavailable,
    answer_applications,
    answer_disk,
    answer_forecast,
    answer_history,
    answer_processes,
    answer_projects,
    answer_ram,
    answer_relations,
    answer_semantic_capability,
    answer_semantic_health,
    answer_semantic_storage,
    answer_system,
)
from .intents import detect_domain, detect_operation, detect_semantic_query


def answer_query(
    snapshot: dict[str, Any] | None,
    query: str,
    previous_snapshot: dict[str, Any] | None = None,
    recent_snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if snapshot is None:
        return unavailable(query, None, "No snapshot is stored yet.")

    lowered = query.lower()
    timestamp = snapshot.get("timestamp")
    system = snapshot.get("system", {})
    availability = snapshot.get("availability", {}).get("system", {})
    history = recent_snapshots or [snapshot]

    # Phase 5: semantic query detection runs first
    semantic_type = detect_semantic_query(lowered)
    if semantic_type == "semantic_capability":
        return answer_semantic_capability(query, snapshot, timestamp)
    if semantic_type == "semantic_health":
        return answer_semantic_health(query, snapshot, timestamp, history)
    if semantic_type == "semantic_storage":
        return answer_semantic_storage(query, snapshot, timestamp)

    domain = detect_domain(lowered)
    if domain is None:
        return unavailable(
            query,
            timestamp,
            "Query domain is not supported by the Phase 1 deterministic query layer.",
        )

    operation = detect_operation(lowered, domain)
    if operation is None:
        return unavailable(
            query,
            timestamp,
            "Query operation is not supported by the Phase 1 deterministic query layer.",
            domain=domain,
        )

    if domain == "applications":
        return answer_applications(query, timestamp, snapshot, availability, operation)

    if domain == "history":
        return answer_history(query, timestamp, snapshot, previous_snapshot, history, operation)

    if domain == "system":
        return answer_system(query, timestamp, snapshot, history, operation)

    if domain == "forecast":
        return answer_forecast(query, timestamp, history, operation)

    if domain == "relations":
        return answer_relations(query, timestamp, snapshot, history, operation)

    if domain == "processes":
        return answer_processes(query, timestamp, system.get("processes", []), availability, operation)

    if domain == "disk":
        return answer_disk(query, timestamp, system.get("disk", {}), availability, operation)

    if domain == "projects":
        # Use the most recent snapshot that has inventory data, not necessarily the latest.
        # Avoids missing folder data when a non-full-system snapshot was collected after
        # a full-system one.
        inventory_snapshot = snapshot
        for candidate in history:
            inv_available = (
                candidate.get("availability", {})
                .get("system", {})
                .get("inventory", {})
                .get("available", False)
            )
            if inv_available:
                inventory_snapshot = candidate
                break
        return answer_projects(
            query,
            timestamp,
            inventory_snapshot,
            inventory_snapshot.get("projects", []),
            operation,
        )

    if domain == "ram":
        return answer_ram(query, timestamp, snapshot, system.get("ram", {}), availability, operation)

    return unavailable(
        query,
        timestamp,
        "Query domain is not supported by the Phase 1 deterministic query layer.",
        domain=domain,
        operation=operation,
    )
