"""Chat session persistence for multi-turn conversations (Phase 9).

Sessions are stored as JSON in ~/.machine-state/sessions/.
They are ephemeral context, not machine state — plain JSON files are correct here.
Sessions older than 30 days are pruned automatically on load.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SESSIONS_DIR = Path.home() / ".machine-state" / "sessions"
_MAX_TURNS = 10
_PRUNE_DAYS = 30


@dataclass
class SessionHistory:
    session_id: str
    created_at: str
    turns: list[dict[str, str]] = field(default_factory=list)

    def add_turn(self, role: str, content: str) -> None:
        self.turns.append({"role": role, "content": content})
        if len(self.turns) > _MAX_TURNS * 2:
            self.turns = self.turns[-(_MAX_TURNS * 2):]

    def context_turns(self) -> list[dict[str, str]]:
        return self.turns[-(_MAX_TURNS * 2):]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "turns": self.turns,
        }


def _session_file(session_id: str) -> Path:
    return _SESSIONS_DIR / f"{session_id}.json"


def new_session() -> SessionHistory:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    return SessionHistory(
        session_id=str(uuid.uuid4())[:8],
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def save_session(session: SessionHistory) -> None:
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _session_file(session.session_id).write_text(
        json.dumps(session.to_dict(), indent=2), encoding="utf-8"
    )


def load_session(session_id: str) -> SessionHistory | None:
    path = _session_file(session_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionHistory(
            session_id=data["session_id"],
            created_at=data["created_at"],
            turns=data.get("turns", []),
        )
    except (json.JSONDecodeError, KeyError):
        return None


def list_sessions() -> list[dict[str, Any]]:
    """Return recent sessions sorted newest first."""
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sessions = []
    for f in sorted(_SESSIONS_DIR.glob("*.json"), reverse=True)[:20]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            sessions.append({
                "session_id": data.get("session_id"),
                "created_at": data.get("created_at"),
                "turn_count": len(data.get("turns", [])) // 2,
            })
        except (json.JSONDecodeError, KeyError):
            pass
    return sessions


def prune_old_sessions() -> int:
    """Delete sessions older than _PRUNE_DAYS. Returns number deleted."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=_PRUNE_DAYS)
    deleted = 0
    for f in _SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            created = datetime.fromisoformat(
                data.get("created_at", "").replace("Z", "+00:00")
            )
            if created < cutoff:
                f.unlink()
                deleted += 1
        except (json.JSONDecodeError, KeyError, ValueError, OSError):
            pass
    return deleted
