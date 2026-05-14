"""Scheduler configuration.

Defines collection intervals per domain and scheduler runtime settings.
All values are in seconds unless noted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..incremental.engine import DOMAIN_INTERVALS
from ..store import DATA_DIR, DEFAULT_DB_PATH

_DEFAULT_PID_FILE = DATA_DIR / "scheduler.pid"
_DEFAULT_LOG_FILE = DATA_DIR / "scheduler.log"


@dataclass
class SchedulerConfig:
    """Runtime configuration for the background scheduler."""

    # Domain-specific collection intervals (seconds)
    domain_intervals: dict[str, int] = field(
        default_factory=lambda: dict(DOMAIN_INTERVALS)
    )

    # Paths to watch as projects (collected at project interval)
    project_paths: list[str] = field(default_factory=list)

    # Maximum processes to collect per snapshot
    process_limit: int = 10

    # Maximum items per project folder
    item_limit: int = 10

    # System inventory limits (only used for inventory domain)
    system_item_limit: int = 15
    system_max_depth: int = 4

    # Scheduler poll interval: how often the loop checks for due domains
    poll_interval_seconds: int = 60

    # Database path
    db_path: str | None = None

    # PID file location (used for daemon management)
    pid_file: Path = field(default_factory=lambda: _DEFAULT_PID_FILE)

    # Log file location
    log_file: Path = field(default_factory=lambda: _DEFAULT_LOG_FILE)

    # Post-collection steps to run (e.g. rebuild memory after collection)
    rebuild_memory_every_n_collections: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_intervals": self.domain_intervals,
            "project_paths": self.project_paths,
            "process_limit": self.process_limit,
            "item_limit": self.item_limit,
            "system_item_limit": self.system_item_limit,
            "system_max_depth": self.system_max_depth,
            "poll_interval_seconds": self.poll_interval_seconds,
            "db_path": self.db_path,
            "pid_file": str(self.pid_file),
            "log_file": str(self.log_file),
            "rebuild_memory_every_n_collections": self.rebuild_memory_every_n_collections,
        }
