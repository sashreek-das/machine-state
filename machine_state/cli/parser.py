"""Argument parser construction for the machine-state CLI."""

from __future__ import annotations

import argparse

from .analysis import _ask_command
from .collection import _collect_command, _tool_command
from .setup_cmd import _setup_command
from .daemon import (
    _events_command,
    _history_command,
    _memory_command,
    _pressure_command,
    _temporal_relations_command,
)
from .forecast import _forecast_command
from .llm import _chat_command, _plan_command
from .scheduler import _notify_command, _scheduler_command, _scheduler_daemon_command
from .semantic import _semantic_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="machine-state")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── setup ─────────────────────────────────────────────────────────────────
    setup_parser = subparsers.add_parser(
        "setup", help="Interactive LLM provider setup wizard."
    )
    setup_parser.set_defaults(func=_setup_command)

    # ── tool ──────────────────────────────────────────────────────────────────
    tool_parser = subparsers.add_parser("tool")
    tool_parser.add_argument(
        "tool_name",
        choices=["ram", "disk", "processes", "project", "largest-items", "system-inventory"],
    )
    tool_parser.add_argument("--path")
    tool_parser.add_argument("--limit", type=int, default=10)
    tool_parser.add_argument("--max-depth", type=int, default=4)
    tool_parser.set_defaults(func=_tool_command)

    # ── collect ───────────────────────────────────────────────────────────────
    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--project", action="append", default=[])
    collect_parser.add_argument("--process-limit", type=int, default=10)
    collect_parser.add_argument("--item-limit", type=int, default=10)
    collect_parser.add_argument("--full-system", action="store_true")
    collect_parser.add_argument("--system-item-limit", type=int, default=15)
    collect_parser.add_argument("--system-max-depth", type=int, default=4)
    collect_parser.add_argument("--db")
    collect_parser.set_defaults(func=_collect_command)

    # ── ask ───────────────────────────────────────────────────────────────────
    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("query")
    ask_parser.add_argument("--db")
    ask_parser.add_argument("--history-limit", type=int, default=12)
    ask_parser.set_defaults(func=_ask_command)

    # ── Phase 4: scheduler ────────────────────────────────────────────────────
    sched_parser = subparsers.add_parser(
        "scheduler", help="Manage the background snapshot scheduler."
    )
    sched_parser.add_argument(
        "scheduler_action",
        choices=["start", "stop", "status", "schedule", "run-once", "install", "uninstall"],
        help=(
            "start: launch daemon | stop: terminate daemon | "
            "status: check if running | schedule: show domain schedules | "
            "run-once: execute one collection cycle now | "
            "install: register as a launchd LaunchAgent (auto-start on login) | "
            "uninstall: remove the LaunchAgent"
        ),
    )
    sched_parser.add_argument("--project", action="append", default=[])
    sched_parser.add_argument("--process-limit", type=int, default=10)
    sched_parser.add_argument("--item-limit", type=int, default=10)
    sched_parser.add_argument("--system-item-limit", type=int, default=15)
    sched_parser.add_argument("--system-max-depth", type=int, default=4)
    sched_parser.add_argument("--db")
    sched_parser.set_defaults(func=_scheduler_command)

    # ── Phase 4: events ───────────────────────────────────────────────────────
    events_parser = subparsers.add_parser("events", help="Query detected system events.")
    events_parser.add_argument("--limit", type=int, default=50, help="Max events to return.")
    events_parser.add_argument("--domain", help="Filter by domain (ram, disk, processes).")
    events_parser.add_argument("--type", help="Filter by event_type.")
    events_parser.add_argument("--db")
    events_parser.set_defaults(func=_events_command)

    # ── Phase 4: pressure ─────────────────────────────────────────────────────
    pressure_parser = subparsers.add_parser("pressure", help="Show live system pressure state.")
    pressure_parser.add_argument(
        "--window", type=int, default=6,
        help="Number of recent snapshots to consider (default: 6).",
    )
    pressure_parser.add_argument("--db")
    pressure_parser.set_defaults(func=_pressure_command)

    # ── Phase 4: entity-history ───────────────────────────────────────────────
    history_parser = subparsers.add_parser(
        "entity-history", help="View behavioral history for a tracked entity."
    )
    history_parser.add_argument(
        "entity_id", nargs="?", default=None,
        help="Entity ID (e.g. 'application:chrome'). Omit to list all tracked entities.",
    )
    history_parser.add_argument("--db")
    history_parser.set_defaults(func=_history_command)

    # ── Phase 4: memory ───────────────────────────────────────────────────────
    memory_parser = subparsers.add_parser(
        "memory", help="Query or rebuild persistent system memory."
    )
    memory_parser.add_argument(
        "key", nargs="?", default=None,
        choices=["heavy-apps", "growing-folders", "ram-spikes", "cleanup", "slowdowns"],
        help="Specific memory key to retrieve. Omit to return all.",
    )
    memory_parser.add_argument(
        "--rebuild", action="store_true",
        help="Recompute all memory from stored snapshots.",
    )
    memory_parser.add_argument("--db")
    memory_parser.set_defaults(func=_memory_command)

    # ── Phase 4: notify ───────────────────────────────────────────────────────
    notify_parser = subparsers.add_parser(
        "notify", help="Evaluate state and send local notifications."
    )
    notify_parser.add_argument(
        "--dry-run", action="store_true",
        help="Show pending notifications without sending them.",
    )
    notify_parser.add_argument("--db")
    notify_parser.set_defaults(func=_notify_command)

    # ── Phase 4: temporal-relations ───────────────────────────────────────────
    temporal_parser = subparsers.add_parser(
        "temporal-relations",
        help="Show temporal relationship evolution across snapshots.",
    )
    temporal_parser.add_argument("--db")
    temporal_parser.set_defaults(func=_temporal_relations_command)

    # ── Phase 5: semantic ─────────────────────────────────────────────────────
    sem_parser = subparsers.add_parser(
        "semantic", help="Semantic machine understanding (Phase 5)."
    )
    sem_parser.add_argument(
        "semantic_action",
        choices=["summary", "pressure", "storage", "app", "capability", "activity"],
        help=(
            "summary: full semantic machine picture | "
            "pressure: semantic pressure states | "
            "storage: storage category breakdown | "
            "app: semantic profile for one application | "
            "capability: what can the machine handle | "
            "activity: user activity patterns"
        ),
    )
    sem_parser.add_argument("--name", dest="app_name", help="Application name (for 'app' action).")
    sem_parser.add_argument(
        "--install-size-gb", type=float, default=0,
        help="Installation size in GB (for 'capability' action).",
    )
    sem_parser.add_argument(
        "--install-app", default=None,
        help="App name for size lookup (for 'capability' action, e.g. 'xcode').",
    )
    sem_parser.add_argument("--db")
    sem_parser.set_defaults(func=_semantic_command)

    # ── Phase 6: plan ─────────────────────────────────────────────────────────
    plan_parser = subparsers.add_parser(
        "plan", help="Planning and tool contract layer (Phase 6)."
    )
    plan_parser.add_argument(
        "plan_action",
        choices=["tools", "detect", "build", "run"],
        help=(
            "tools: list all registered tool contracts | "
            "detect: detect the intent for a query | "
            "build: build an execution plan for a query | "
            "run: build and execute a plan, returning aggregated results"
        ),
    )
    plan_parser.add_argument(
        "query", nargs="?", default="",
        help="Query string (required for detect, build, run actions).",
    )
    plan_parser.add_argument("--db")
    plan_parser.set_defaults(func=_plan_command)

    # ── Phase 8: forecast ─────────────────────────────────────────────────────
    forecast_parser = subparsers.add_parser(
        "forecast",
        help="Predictive intelligence: disk growth, RAM trajectory, risk trends (Phase 8).",
    )
    forecast_parser.add_argument(
        "forecast_action",
        choices=["disk", "ram", "workload", "trends", "install"],
        help=(
            "disk: disk exhaustion forecast + folder hotspots | "
            "ram: RAM trajectory prediction + pressure windows | "
            "workload: workload patterns + slowdown windows | "
            "trends: risk score + app trends + proactive insights | "
            "install: simulate install impact"
        ),
    )
    forecast_parser.add_argument(
        "--size-gb", type=float, default=0.0, dest="size_gb",
        help="Installation size in GB (for 'install' action).",
    )
    forecast_parser.add_argument(
        "--limit", type=int, default=5,
        help="Number of items to return (for 'disk' and 'trends' actions, default 5).",
    )
    forecast_parser.add_argument("--db")
    forecast_parser.set_defaults(func=_forecast_command)

    # ── hidden: scheduler daemon entry point (PyInstaller mode) ──────────────
    # Not shown in help. Invoked internally by scheduler/daemon.py when frozen.
    daemon_parser = subparsers.add_parser("_scheduler-daemon")
    daemon_parser.add_argument("config_json")
    daemon_parser.set_defaults(func=_scheduler_daemon_command)

    # ── Phase 7: chat ─────────────────────────────────────────────────────────
    chat_parser = subparsers.add_parser(
        "chat", help="Ask a question and get a natural language answer from the LLM (Phase 7)."
    )
    chat_parser.add_argument("query", help="Natural language question about your machine.")
    chat_parser.add_argument(
        "--provider", default=None,
        choices=["anthropic", "openai", "gemini", "ollama"],
        help="LLM provider to use (default: read from `machine-state setup` config, then ollama).",
    )
    chat_parser.add_argument(
        "--model", default=None,
        help="Model name override (e.g. 'claude-opus-4-6', 'gpt-4o', 'gemini-2.0-flash', 'llama3').",
    )
    chat_parser.add_argument(
        "--base-url", default=None, dest="base_url",
        help="Base URL override (useful for Ollama or local proxies).",
    )
    chat_parser.add_argument(
        "--raw", action="store_true",
        help="Output full JSON response including context and token counts.",
    )
    chat_parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show intent, provider, and token info after the response.",
    )
    chat_parser.add_argument("--db")
    chat_parser.set_defaults(func=_chat_command)

    return parser
