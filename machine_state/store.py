"""SQLite-backed local snapshot store."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


DATA_DIR = Path.home() / ".machine-state"
DEFAULT_DB_PATH = DATA_DIR / "machine_state.sqlite3"

# Tracks which DB paths have already had their schema initialized in this process.
# Avoids re-running CREATE TABLE IF NOT EXISTS DDL on every read/write call.
_initialized: set[str] = set()


def _connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    resolved = Path(db_path or DEFAULT_DB_PATH)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(resolved, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def initialize(db_path: str | Path | None = None) -> None:
    """Create all tables. No-op if already done in this process for this path."""
    resolved = str(Path(db_path or DEFAULT_DB_PATH).resolve())
    if resolved in _initialized:
        return
    with _connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL UNIQUE,
                snapshot_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                domain TEXT NOT NULL,
                summary TEXT NOT NULL,
                evidence_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS entity_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                metrics_json TEXT NOT NULL,
                UNIQUE(entity_id, timestamp)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS system_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                updated_at TEXT NOT NULL,
                value_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS domain_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL UNIQUE,
                last_collected_at TEXT,
                interval_seconds INTEGER NOT NULL,
                next_due_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                notification_key TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL
            )
            """
        )
        # Phase 9: composite health score persisted after each scheduler cycle
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS health_scores (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          INTEGER NOT NULL,
                score       INTEGER NOT NULL,
                label       TEXT NOT NULL,
                ram_score   INTEGER NOT NULL,
                disk_score  INTEGER NOT NULL,
                proc_score  INTEGER NOT NULL,
                event_score INTEGER NOT NULL,
                fcast_score INTEGER NOT NULL
            )
            """
        )
        # Phase 9: log of files deleted by the cleanup engine
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS cleanup_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                ts         INTEGER NOT NULL,
                path       TEXT NOT NULL,
                category   TEXT NOT NULL,
                size_bytes INTEGER NOT NULL
            )
            """
        )
        connection.commit()
    _initialized.add(resolved)


def initialize_phase4_tables(db_path: str | Path | None = None) -> None:
    """Alias kept for backward compatibility — all tables are now created in initialize()."""
    initialize(db_path)


def save_snapshot(snapshot: dict[str, Any], db_path: str | Path | None = None) -> dict[str, Any]:
    initialize(db_path)
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT INTO snapshots (timestamp, snapshot_json) VALUES (?, ?)",
            (snapshot["timestamp"], json.dumps(snapshot, sort_keys=True)),
        )
        connection.commit()

    return {
        "timestamp": snapshot["timestamp"],
        "stored": True,
    }


def get_latest_snapshot(db_path: str | Path | None = None) -> dict[str, Any] | None:
    initialize(db_path)
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT snapshot_json FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if row is None:
        return None

    return json.loads(row["snapshot_json"])


def get_recent_snapshots(limit: int = 2, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    initialize(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT snapshot_json FROM snapshots ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    return [json.loads(row["snapshot_json"]) for row in rows]


def get_all_snapshots(
    db_path: str | Path | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    initialize(db_path)
    with _connect(db_path) as connection:
        if limit is not None:
            rows = connection.execute(
                "SELECT snapshot_json FROM snapshots ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [json.loads(row["snapshot_json"]) for row in reversed(rows)]
        rows = connection.execute(
            "SELECT snapshot_json FROM snapshots ORDER BY id ASC"
        ).fetchall()
    return [json.loads(row["snapshot_json"]) for row in rows]


# ── Events ────────────────────────────────────────────────────────────────────

def save_event(event: dict[str, Any], db_path: str | Path | None = None) -> None:
    initialize(db_path)
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO events (timestamp, event_type, severity, domain, summary, evidence_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event["timestamp"],
                event["event_type"],
                event["severity"],
                event["domain"],
                event["summary"],
                json.dumps(event.get("evidence", {}), sort_keys=True),
            ),
        )
        connection.commit()


def get_events(
    limit: int = 50,
    domain: str | None = None,
    event_type: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    initialize(db_path)
    params: list[Any] = []
    if domain and event_type:
        query = "SELECT * FROM events WHERE domain = ? AND event_type = ? ORDER BY timestamp DESC LIMIT ?"
        params = [domain, event_type, limit]
    elif domain:
        query = "SELECT * FROM events WHERE domain = ? ORDER BY timestamp DESC LIMIT ?"
        params = [domain, limit]
    elif event_type:
        query = "SELECT * FROM events WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?"
        params = [event_type, limit]
    else:
        query = "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?"
        params = [limit]
    with _connect(db_path) as connection:
        rows = connection.execute(query, params).fetchall()
    return [
        {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "event_type": row["event_type"],
            "severity": row["severity"],
            "domain": row["domain"],
            "summary": row["summary"],
            "evidence": json.loads(row["evidence_json"]),
        }
        for row in rows
    ]


# ── Entity snapshots ──────────────────────────────────────────────────────────

def save_entity_snapshot(
    entity_id: str,
    entity_type: str,
    timestamp: str,
    metrics: dict[str, Any],
    db_path: str | Path | None = None,
) -> None:
    initialize(db_path)
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO entity_snapshots (entity_id, entity_type, timestamp, metrics_json)
            VALUES (?, ?, ?, ?)
            """,
            (entity_id, entity_type, timestamp, json.dumps(metrics, sort_keys=True)),
        )
        connection.commit()


def get_entity_history(
    entity_id: str,
    limit: int = 100,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    initialize(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp, entity_type, metrics_json
            FROM entity_snapshots
            WHERE entity_id = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (entity_id, limit),
        ).fetchall()
    return [
        {
            "entity_id": entity_id,
            "entity_type": row["entity_type"],
            "timestamp": row["timestamp"],
            "metrics": json.loads(row["metrics_json"]),
        }
        for row in rows
    ]


def get_tracked_entity_ids(db_path: str | Path | None = None) -> list[str]:
    initialize(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT DISTINCT entity_id, entity_type FROM entity_snapshots ORDER BY entity_id"
        ).fetchall()
    return [{"entity_id": row["entity_id"], "entity_type": row["entity_type"]} for row in rows]


# ── System memory ─────────────────────────────────────────────────────────────

def save_system_memory(
    key: str,
    value: Any,
    updated_at: str,
    db_path: str | Path | None = None,
) -> None:
    initialize(db_path)
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO system_memory (key, updated_at, value_json)
            VALUES (?, ?, ?)
            """,
            (key, updated_at, json.dumps(value, sort_keys=True)),
        )
        connection.commit()


def get_system_memory(key: str, db_path: str | Path | None = None) -> Any | None:
    initialize(db_path)
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT value_json FROM system_memory WHERE key = ?",
            (key,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["value_json"])


def get_all_system_memory(db_path: str | Path | None = None) -> dict[str, Any]:
    initialize(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT key, updated_at, value_json FROM system_memory ORDER BY key"
        ).fetchall()
    return {
        row["key"]: {
            "updated_at": row["updated_at"],
            "value": json.loads(row["value_json"]),
        }
        for row in rows
    }


# ── Domain schedules ──────────────────────────────────────────────────────────

def save_domain_schedule(
    domain: str,
    last_collected_at: str,
    interval_seconds: int,
    next_due_at: str,
    db_path: str | Path | None = None,
) -> None:
    initialize(db_path)
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO domain_schedules
                (domain, last_collected_at, interval_seconds, next_due_at)
            VALUES (?, ?, ?, ?)
            """,
            (domain, last_collected_at, interval_seconds, next_due_at),
        )
        connection.commit()


def get_domain_schedules(db_path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    initialize(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT domain, last_collected_at, interval_seconds, next_due_at FROM domain_schedules"
        ).fetchall()
    return {
        row["domain"]: {
            "last_collected_at": row["last_collected_at"],
            "interval_seconds": row["interval_seconds"],
            "next_due_at": row["next_due_at"],
        }
        for row in rows
    }


# ── Notification log ──────────────────────────────────────────────────────────

def save_notification_log(
    timestamp: str,
    notification_key: str,
    title: str,
    body: str,
    db_path: str | Path | None = None,
) -> None:
    initialize(db_path)
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO notification_log (timestamp, notification_key, title, body)
            VALUES (?, ?, ?, ?)
            """,
            (timestamp, notification_key, title, body),
        )
        connection.commit()


def get_last_notification_time(
    notification_key: str,
    db_path: str | Path | None = None,
) -> str | None:
    initialize(db_path)
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT timestamp FROM notification_log
            WHERE notification_key = ?
            ORDER BY timestamp DESC LIMIT 1
            """,
            (notification_key,),
        ).fetchone()
    return row["timestamp"] if row else None


# ── Health scores ─────────────────────────────────────────────────────────────

def save_health_score(record: dict[str, Any], db_path: str | Path | None = None) -> None:
    initialize(db_path)
    c = record.get("components", {})
    with _connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO health_scores
                (ts, score, label, ram_score, disk_score, proc_score, event_score, fcast_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("ts", 0),
                record.get("score", 0),
                record.get("label", ""),
                c.get("ram", 0),
                c.get("disk", 0),
                c.get("process", 0),
                c.get("events", 0),
                c.get("forecast", 0),
            ),
        )
        connection.commit()


def get_health_scores(
    limit: int = 10,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    initialize(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM health_scores ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "ts": row["ts"],
            "score": row["score"],
            "label": row["label"],
            "components": {
                "ram": row["ram_score"],
                "disk": row["disk_score"],
                "process": row["proc_score"],
                "events": row["event_score"],
                "forecast": row["fcast_score"],
            },
        }
        for row in rows
    ]


# ── Cleanup log ───────────────────────────────────────────────────────────────

def log_cleanup_deletion(
    path: str,
    category: str,
    size_bytes: int,
    db_path: str | Path | None = None,
) -> None:
    import time as _time
    initialize(db_path)
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT INTO cleanup_log (ts, path, category, size_bytes) VALUES (?, ?, ?, ?)",
            (int(_time.time()), path, category, size_bytes),
        )
        connection.commit()


def get_cleanup_log(
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    initialize(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT ts, path, category, size_bytes FROM cleanup_log ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {"ts": row["ts"], "path": row["path"], "category": row["category"],
         "size_bytes": row["size_bytes"]}
        for row in rows
    ]


# ── Snapshot by time ──────────────────────────────────────────────────────────

def get_snapshot_before(
    iso_timestamp: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return the latest snapshot with timestamp <= iso_timestamp."""
    initialize(db_path)
    with _connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT snapshot_json FROM snapshots
            WHERE timestamp <= ?
            ORDER BY timestamp DESC LIMIT 1
            """,
            (iso_timestamp,),
        ).fetchone()
    return json.loads(row["snapshot_json"]) if row else None
