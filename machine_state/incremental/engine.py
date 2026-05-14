"""Domain-aware incremental snapshot engine.

Tracks collection intervals per domain and builds partial snapshots
collecting only the domains that are due, avoiding expensive full rescans.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .. import store

# Default collection intervals in seconds per domain
DOMAIN_INTERVALS: dict[str, int] = {
    "ram": 5 * 60,         # 5 minutes — cheap, frequent
    "processes": 5 * 60,   # 5 minutes — cheap, frequent
    "disk": 15 * 60,       # 15 minutes — moderate cost
    "projects": 15 * 60,   # 15 minutes — moderate cost
    "inventory": 60 * 60,  # 60 minutes — expensive full scan
}

_ALL_DOMAINS = list(DOMAIN_INTERVALS.keys())


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_due_domains(db_path: str | None = None) -> list[str]:
    """Return list of domains due for collection right now.

    A domain is due if it has never been collected or its next_due_at
    timestamp has passed.
    """
    schedules = store.get_domain_schedules(db_path)
    now_str = _now_utc().isoformat()
    due: list[str] = []
    for domain in _ALL_DOMAINS:
        info = schedules.get(domain)
        if info is None:
            # Never collected — always due
            due.append(domain)
            continue
        next_due = info.get("next_due_at")
        if not next_due or now_str >= next_due:
            due.append(domain)
    return due


def record_domain_collection(
    domain: str,
    collected_at: str | None = None,
    db_path: str | None = None,
) -> None:
    """Record that a domain was just collected and compute next due time."""
    now = _now_utc()
    collected_str = collected_at or now.isoformat()
    interval = DOMAIN_INTERVALS.get(domain, 15 * 60)
    collected_dt = _parse_iso(collected_str) or now
    next_due = (collected_dt + timedelta(seconds=interval)).isoformat()
    store.save_domain_schedule(domain, collected_str, interval, next_due, db_path)


def build_incremental_snapshot(
    due_domains: list[str],
    project_paths: list[str] | None = None,
    process_limit: int = 10,
    item_limit: int = 10,
    system_item_limit: int = 15,
    system_max_depth: int = 4,
) -> dict[str, Any]:
    """Build a snapshot collecting only the specified due domains.

    Domains not in due_domains are skipped, reducing expensive operations.
    - ram / processes: controls process collection
    - disk: controls disk usage probe
    - projects: controls project folder analysis
    - inventory: controls full system filesystem scan
    """
    from .. import snapshot as snap_module

    collect_system = "ram" in due_domains or "processes" in due_domains
    collect_disk = "disk" in due_domains
    collect_projects = "projects" in due_domains and bool(project_paths)
    collect_inventory = "inventory" in due_domains

    # We always need at least ram/disk for derived metrics to be meaningful
    return snap_module.build_snapshot(
        project_paths=project_paths if collect_projects else [],
        process_limit=process_limit if collect_system else 0,
        item_limit=item_limit if collect_projects else 0,
        full_system=collect_inventory,
        system_item_limit=system_item_limit if collect_inventory else 0,
        system_max_depth=system_max_depth if collect_inventory else 0,
    )


def get_schedule_status(db_path: str | None = None) -> list[dict[str, Any]]:
    """Return current schedule status for all domains."""
    schedules = store.get_domain_schedules(db_path)
    now_str = _now_utc().isoformat()
    result: list[dict[str, Any]] = []
    for domain in _ALL_DOMAINS:
        info = schedules.get(domain)
        interval = DOMAIN_INTERVALS[domain]
        if info is None:
            result.append(
                {
                    "domain": domain,
                    "interval_seconds": interval,
                    "last_collected_at": None,
                    "next_due_at": None,
                    "overdue": True,
                    "status": "never_collected",
                }
            )
        else:
            next_due = info.get("next_due_at")
            overdue = (not next_due) or (now_str >= next_due)
            result.append(
                {
                    "domain": domain,
                    "interval_seconds": interval,
                    "last_collected_at": info.get("last_collected_at"),
                    "next_due_at": next_due,
                    "overdue": overdue,
                    "status": "overdue" if overdue else "scheduled",
                }
            )
    return result
