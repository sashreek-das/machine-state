"""Live ANSI terminal dashboard.

Reads directly from SQLite — no subprocess per refresh.
Redraws on a fixed interval; exits on 'q'.
"""

from __future__ import annotations

import os
import select as _sel
import sys
import termios
import tty
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import store
from ..health import compute_health_score
from ..constants import GB, MB

# ── ANSI ──────────────────────────────────────────────────────────────────────
_R  = "\033[0m"
_B  = "\033[1m"
_D  = "\033[2m"
_CY = "\033[1;36m"
_GR = "\033[1;32m"
_YL = "\033[1;33m"
_RD = "\033[1;31m"

_BOX_W = 54


def _w(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def _fmt_bytes(n: int) -> str:
    if n >= GB:
        return f"{n / GB:.1f} GB"
    if n >= MB:
        return f"{n / MB:.0f} MB"
    return f"{n / 1024:.0f} KB"


def _bar(ratio: float, width: int = 20) -> str:
    ratio = max(0.0, min(1.0, ratio))
    filled = int(ratio * width)
    empty  = width - filled
    if ratio >= 0.90:
        colour = _RD
    elif ratio >= 0.75:
        colour = _YL
    else:
        colour = _GR
    return f"{colour}{'█' * filled}{_D}{'░' * empty}{_R}"


def _pressure_colour(level: str) -> str:
    return {
        "critical": _RD, "high": _RD,
        "moderate": _YL, "elevated": _YL,
        "low": _GR, "normal": _GR,
    }.get(level, _D)


def _score_colour(score: int) -> str:
    if score >= 85:
        return _GR
    if score >= 65:
        return _YL
    return _RD


def _trend_arrow(scores: list[dict[str, Any]]) -> str:
    if len(scores) < 2:
        return ""
    delta = scores[0]["score"] - scores[-1]["score"]
    if delta > 3:
        return f" {_GR}↑{_R}"
    if delta < -3:
        return f" {_RD}↓{_R}"
    return f" {_D}→{_R}"


def _fetch(db_path: str | Path | None) -> dict[str, Any]:
    snapshots = store.get_recent_snapshots(limit=12, db_path=db_path)
    events    = store.get_events(limit=20, db_path=db_path)
    scores    = store.get_health_scores(limit=5, db_path=db_path)
    health    = compute_health_score(snapshots, events)
    latest    = snapshots[0] if snapshots else {}
    return {
        "health": health, "scores": scores,
        "latest": latest, "events": events[:5],
        "snapshots": snapshots,
    }


def _render(data: dict[str, Any]) -> None:
    health  = data["health"]
    latest  = data["latest"]
    events  = data["events"]
    scores  = data["scores"]
    score   = health["score"]
    sc      = _score_colour(score)
    trend   = _trend_arrow(scores)
    now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

    _w("\033[2J\033[H")  # clear + home

    # Header
    pad = _BOX_W - len("machine state  ·  live") - len("[q] quit") - 4
    _w(f"  ╭{'─' * _BOX_W}╮\n")
    _w(f"  │  {_B}machine state  ·  live{_R}{' ' * pad}{_D}[q] quit{_R}  │\n")
    _w(f"  ╰{'─' * _BOX_W}╯\n\n")

    # Health score
    _w(f"  {_B}Health{_R}  {_bar(score / 100, 16)}  "
       f"{sc}{_B}{score}{_R} / 100  {sc}{health['label']}{_R}{trend}\n")
    _w(f"  {_D}Updated {now_str}{_R}\n\n")
    _w(f"  {_D}{'─' * _BOX_W}{_R}\n\n")

    # RAM
    ram   = latest.get("system", {}).get("ram", {})
    total_ram  = int(ram.get("totalBytes") or 0)
    used_ram   = int(ram.get("usedBytes") or 0)
    ram_ratio  = used_ram / total_ram if total_ram else 0
    ram_level  = "low"
    if ram_ratio >= 0.90:
        ram_level = "critical"
    elif ram_ratio >= 0.75:
        ram_level = "high"
    elif ram_ratio >= 0.50:
        ram_level = "moderate"
    pc = _pressure_colour(ram_level)
    _w(f"  {_B}RAM{_R}   {_bar(ram_ratio)}  "
       f"{_fmt_bytes(used_ram)} / {_fmt_bytes(total_ram)}   "
       f"{pc}{ram_level}{_R}\n")

    # Disk
    disk  = latest.get("system", {}).get("disk", {})
    total_disk = int(disk.get("totalBytes") or 0)
    used_disk  = int(disk.get("usedBytes") or 0)
    disk_ratio = used_disk / total_disk if total_disk else 0
    disk_level = "low"
    if disk_ratio >= 0.92:
        disk_level = "critical"
    elif disk_ratio >= 0.85:
        disk_level = "high"
    elif disk_ratio >= 0.65:
        disk_level = "moderate"
    pc = _pressure_colour(disk_level)
    _w(f"  {_B}Disk{_R}  {_bar(disk_ratio)}  "
       f"{_fmt_bytes(used_disk)} / {_fmt_bytes(total_disk)}   "
       f"{pc}{disk_level}{_R}\n\n")

    # Top processes
    _w(f"  {_D}{'─' * _BOX_W}{_R}\n\n")
    _w(f"  {_B}Top processes{_R}\n")
    apps = latest.get("derived", {}).get("applications", [])[:5]
    for app in apps:
        name = str(app.get("application", "?"))[:18]
        mem  = int(app.get("totalMemoryBytes") or 0)
        pct  = f"{int(mem / total_ram * 100)}%" if total_ram else "?"
        _w(f"  {name:<20} {_fmt_bytes(mem):<10} {_D}{pct}{_R}\n")

    # Recent events
    _w(f"\n  {_D}{'─' * _BOX_W}{_R}\n\n")
    _w(f"  {_B}Recent events{_R}\n")
    if events:
        for e in events:
            try:
                ts = datetime.fromisoformat(
                    e["timestamp"].replace("Z", "+00:00")
                ).strftime("%H:%M")
            except ValueError:
                ts = "??:??"
            sev = e.get("severity", "")
            col = _RD if sev == "critical" else (_YL if sev == "elevated" else _D)
            _w(f"  {_D}{ts}{_R}  {col}{e.get('summary', '')}{_R}\n")
    else:
        _w(f"  {_D}No recent events.{_R}\n")

    _w(f"\n  {_D}{'─' * _BOX_W}{_R}\n")
    _w(f"\n  {_D}Refreshes every {data.get('interval', 5)}s · q to quit{_R}\n")


def _poll_quit(timeout: float) -> bool:
    """Return True if 'q' or Ctrl-C pressed within timeout seconds."""
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ready, _, _ = _sel.select([fd], [], [], timeout)
        if ready:
            b = os.read(fd, 1)
            return b in (b'q', b'Q', b'\x03')
        return False
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def run_dashboard(
    db_path: str | Path | None = None,
    interval: int = 5,
) -> None:
    """Run the live dashboard until the user presses 'q'."""
    _w("\033[?25l")  # hide cursor
    try:
        while True:
            data = _fetch(db_path)
            data["interval"] = interval
            _render(data)
            if _poll_quit(float(interval)):
                break
    finally:
        _w("\033[?25h\033[2J\033[H")  # show cursor, clear
