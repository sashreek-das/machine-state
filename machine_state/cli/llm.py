"""CLI handlers for Phase 6–7 LLM/planner commands: plan and chat."""

from __future__ import annotations

import argparse

from .. import store
from ._utils import _print_json


def _plan_command(args: argparse.Namespace) -> int:
    from ..planner.intents import detect_intent
    from ..planner.planner import build_plan, execute_plan
    from ..planner.contracts import list_tools

    if args.plan_action == "tools":
        tools_list = [
            {
                "name": t.name,
                "description": t.description,
                "safe": t.safe,
                "parameters": {
                    k: {
                        "type": v.type,
                        "required": v.required,
                        "description": v.description,
                        "default": v.default,
                    }
                    for k, v in t.schema.parameters.items()
                },
                "outputDescription": t.output_description,
            }
            for t in list_tools()
        ]
        _print_json({"tools": tools_list, "count": len(tools_list)})
        return 0

    if args.plan_action == "detect":
        intent = detect_intent(args.query)
        _print_json({
            "intent": intent.name,
            "description": intent.description,
            "tools": intent.tools,
            "parameters": intent.parameters,
        })
        return 0

    if args.plan_action == "build":
        plan = build_plan(args.query)
        _print_json({
            "intent": plan.intent,
            "intentDescription": plan.intent_description,
            "query": plan.query,
            "steps": [
                {"tool": s.tool_name, "arguments": s.arguments}
                for s in plan.steps
            ],
        })
        return 0

    if args.plan_action == "run":
        recent_snapshots = store.get_recent_snapshots(limit=12, db_path=args.db)
        latest_snapshot = recent_snapshots[0] if recent_snapshots else None
        if not latest_snapshot:
            _print_json({"status": "no_data", "reason": "No snapshots available."})
            return 1

        db_path = args.db or str(store.DEFAULT_DB_PATH)
        plan = build_plan(args.query)
        result = execute_plan(plan, latest_snapshot, recent_snapshots, db_path)
        _print_json({
            "intent": result.intent,
            "query": result.query,
            "status": result.status,
            "aggregated": result.aggregated,
            "steps": result.steps,
        })
        return 0

    _print_json({"status": "error", "reason": f"Unknown plan action: {args.plan_action}"})
    return 1


def _resolve_provider(args: argparse.Namespace) -> tuple[str, dict]:
    from .. import config as _config
    if args.provider is not None:
        kwargs: dict = {}
        if args.model:
            kwargs["model"] = args.model
        if args.base_url:
            kwargs["base_url"] = args.base_url
        return args.provider, kwargs
    name, kwargs = _config.provider_kwargs()
    if args.model:
        kwargs["model"] = args.model
    if args.base_url:
        kwargs["base_url"] = args.base_url
    return name, kwargs


def _chat_command(args: argparse.Namespace) -> int:
    from ..llm.providers import get_provider
    from ..llm.orchestrator import explain
    from .. import config as _config

    recent_snapshots = store.get_recent_snapshots(limit=12, db_path=args.db)
    latest_snapshot  = recent_snapshots[0] if recent_snapshots else None
    if not latest_snapshot:
        _print_json({"status": "no_data", "reason": "No snapshots available. Run: collect"})
        return 1

    db_path = args.db or str(store.DEFAULT_DB_PATH)
    provider_name, provider_kwargs = _resolve_provider(args)

    if provider_name == "ollama" and not _config.load():
        print("No LLM configured. Run `machine-state setup` first.",
              file=__import__("sys").stderr)

    try:
        provider = get_provider(provider_name, **provider_kwargs)
    except Exception as exc:
        _print_json({"status": "error", "reason": str(exc)})
        return 1

    # One-shot mode when a query is provided
    if args.query:
        try:
            result = explain(args.query, latest_snapshot, recent_snapshots, db_path, provider)
        except Exception as exc:
            _print_json({"status": "error", "reason": str(exc)})
            return 1
        if args.raw:
            _print_json(result)
        else:
            print(result["response"])
            if args.verbose:
                print(f"\n[intent: {result.get('intent')} | "
                      f"provider: {result.get('provider')}/{result.get('model')} | "
                      f"tokens: {result.get('tokens', {}).get('total', '?')}]")
        return 0

    # Interactive session mode (no query given)
    return _chat_session(
        latest_snapshot, recent_snapshots, db_path, provider,
        raw=args.raw, verbose=args.verbose,
    )


def _chat_session(
    latest: dict,
    recent: list,
    db_path: str,
    provider: object,
    raw: bool = False,
    verbose: bool = False,
) -> int:
    """Multi-turn interactive chat REPL."""
    import sys
    from ..llm.orchestrator import explain
    from ..session import new_session, save_session, prune_old_sessions

    prune_old_sessions()
    session = new_session()

    print(f"\n  \033[1mmachine state chat\033[0m  "
          f"\033[2m(session {session.session_id} · ctrl-c or 'quit' to exit)\033[0m\n")

    while True:
        try:
            query = input("  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            break

        session.add_turn("user", query)
        try:
            result = explain(query, latest, recent, db_path, provider)
        except Exception as exc:
            print(f"\n  \033[31mError: {exc}\033[0m\n")
            continue

        response = result.get("response", "")
        session.add_turn("assistant", response)
        save_session(session)

        print(f"\n  \033[1;36m◆\033[0m  {response}\n")
        if verbose:
            print(f"  \033[2m[intent: {result.get('intent')} | "
                  f"tokens: {result.get('tokens', {}).get('total', '?')}]\033[0m\n")

    return 0
