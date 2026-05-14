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


def _chat_command(args: argparse.Namespace) -> int:
    from ..llm.providers import get_provider
    from ..llm.orchestrator import explain

    recent_snapshots = store.get_recent_snapshots(limit=12, db_path=args.db)
    latest_snapshot = recent_snapshots[0] if recent_snapshots else None
    if not latest_snapshot:
        _print_json({"status": "no_data", "reason": "No snapshots available. Run: collect"})
        return 1

    db_path = args.db or str(store.DEFAULT_DB_PATH)

    try:
        provider_kwargs: dict = {}
        if args.model:
            provider_kwargs["model"] = args.model
        if args.base_url:
            provider_kwargs["base_url"] = args.base_url
        provider = get_provider(args.provider, **provider_kwargs)
    except Exception as exc:
        _print_json({"status": "error", "reason": str(exc)})
        return 1

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
            print()
            print(f"[intent: {result.get('intent')} | "
                  f"provider: {result.get('provider')}/{result.get('model')} | "
                  f"tokens: {result.get('tokens', {}).get('total', '?')}]")

    return 0
