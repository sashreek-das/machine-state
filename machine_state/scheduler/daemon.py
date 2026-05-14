"""Daemon management: start, stop, status.

The scheduler runs as a background Python thread within a subprocess.
A PID file is used to track the running process.

Start:  forks a new process running the scheduler loop
Stop:   sends SIGTERM to the tracked PID
Status: checks whether the PID is still alive
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import SchedulerConfig


def _read_pid(pid_file: Path) -> int | None:
    try:
        return int(pid_file.read_text().strip())
    except (OSError, ValueError):
        return None


def _write_pid(pid_file: Path, pid: int) -> None:
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(pid))


def _clear_pid(pid_file: Path) -> None:
    try:
        pid_file.unlink()
    except OSError:
        pass


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def start_daemon(config: SchedulerConfig) -> dict[str, Any]:
    """Start the scheduler daemon in a background subprocess.

    Returns a status dict with pid and status.
    """
    pid_file = config.pid_file

    # Check if already running
    existing_pid = _read_pid(pid_file)
    if existing_pid is not None and _is_alive(existing_pid):
        return {
            "status": "already_running",
            "pid": existing_pid,
            "message": f"Scheduler is already running (PID {existing_pid}).",
        }

    if getattr(sys, "frozen", False):
        # PyInstaller onefile: re-spawning the binary races against the parent's
        # atexit cleanup deleting the extraction dir (_MEIPASS) before the child
        # finishes bootstrapping.  Fork instead — the child inherits the already-
        # loaded Python runtime and all imported modules; no re-extraction needed.
        from ..scheduler.runner import run_scheduler_loop  # import before fork

        pid = os.fork()
        if pid == 0:
            # Child: detach from the parent's session and run the scheduler loop.
            os.setsid()
            dev_null = os.open(os.devnull, os.O_RDWR)
            for fd in (0, 1, 2):
                os.dup2(dev_null, fd)
            os.close(dev_null)
            run_scheduler_loop(config)
            os._exit(0)

        # Parent: record the child PID and return immediately.
        _write_pid(pid_file, pid)
        return {
            "status": "started",
            "pid": pid,
            "message": f"Scheduler started (PID {pid}).",
            "pidFile": str(pid_file),
            "logFile": str(config.log_file),
        }

    # Non-frozen (regular Python): spawn a subprocess running the scheduler loop.
    config_json = json.dumps(config.to_dict())
    launch_script = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from machine_state.scheduler.config import SchedulerConfig\n"
        "from machine_state.scheduler.runner import run_scheduler_loop\n"
        "cfg_dict = json.loads(sys.argv[1])\n"
        "cfg = SchedulerConfig(**{\n"
        "    k: v for k, v in cfg_dict.items()\n"
        "    if k not in ('pid_file', 'log_file')\n"
        "})\n"
        "cfg.pid_file = Path(cfg_dict['pid_file'])\n"
        "cfg.log_file = Path(cfg_dict['log_file'])\n"
        "run_scheduler_loop(cfg)\n"
    )
    log_path = str(config.log_file)
    with open(log_path, "a") as log_fh:
        process = subprocess.Popen(
            [sys.executable, "-c", launch_script, config_json],
            start_new_session=True,
            stdout=log_fh,
            stderr=log_fh,
        )

    _write_pid(pid_file, process.pid)
    return {
        "status": "started",
        "pid": process.pid,
        "message": f"Scheduler started (PID {process.pid}).",
        "pidFile": str(pid_file),
        "logFile": str(config.log_file),
    }


def stop_daemon(config: SchedulerConfig) -> dict[str, Any]:
    """Stop the running scheduler daemon.

    Sends SIGTERM and clears the PID file.
    """
    pid_file = config.pid_file
    pid = _read_pid(pid_file)

    if pid is None:
        return {
            "status": "not_running",
            "message": "No PID file found. Scheduler may not be running.",
        }

    if not _is_alive(pid):
        _clear_pid(pid_file)
        return {
            "status": "not_running",
            "message": f"PID {pid} is no longer alive. Cleared stale PID file.",
        }

    try:
        os.kill(pid, signal.SIGTERM)
        _clear_pid(pid_file)
        return {
            "status": "stopped",
            "pid": pid,
            "message": f"Sent SIGTERM to scheduler (PID {pid}).",
        }
    except OSError as exc:
        return {
            "status": "error",
            "pid": pid,
            "message": f"Failed to stop scheduler: {exc}",
        }


def get_status(config: SchedulerConfig) -> dict[str, Any]:
    """Return the current status of the scheduler daemon."""
    pid_file = config.pid_file
    pid = _read_pid(pid_file)

    if pid is None:
        return {
            "running": False,
            "status": "stopped",
            "message": "Scheduler is not running.",
        }

    alive = _is_alive(pid)
    if not alive:
        _clear_pid(pid_file)
        return {
            "running": False,
            "status": "stopped",
            "message": f"PID {pid} is no longer alive. Stale PID file removed.",
        }

    return {
        "running": True,
        "status": "running",
        "pid": pid,
        "pidFile": str(pid_file),
        "logFile": str(config.log_file),
        "message": f"Scheduler is running (PID {pid}).",
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }
