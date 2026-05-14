"""Incremental snapshot engine — domain-aware selective collection."""

from .engine import (
    DOMAIN_INTERVALS,
    get_due_domains,
    record_domain_collection,
    build_incremental_snapshot,
    get_schedule_status,
)

__all__ = [
    "DOMAIN_INTERVALS",
    "get_due_domains",
    "record_domain_collection",
    "build_incremental_snapshot",
    "get_schedule_status",
]
