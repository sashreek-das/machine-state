"""LLM-based tool selection.

Replaces regex intent detection for the chat/ask pipeline.
The LLM reads all registered tool descriptions and selects
which tools to call for a given natural language query.

This module is part of the planner (LLM) layer and must never be
imported from any deterministic runtime module (snapshot, store,
pressure, events, incremental, scheduler).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from .contracts import TOOL_REGISTRY
from .intents import Intent, _DESCRIPTIONS, detect_intent
from .validators import validate_arguments

if TYPE_CHECKING:
    from ..llm.providers.base import LLMProvider


# ── Prompt construction ────────────────────────────────────────────────────────

def _build_tool_listing() -> str:
    return "\n".join(
        f"- {name}: {tool.description}"
        for name, tool in TOOL_REGISTRY.items()
    )


_TOOL_LISTING: str = _build_tool_listing()

_KNOWN_INTENTS: str = (
    "install_feasibility, compatibility_check, slowdown_analysis, health_check, "
    "pressure_analysis, storage_cleanup_advice, activity_analysis, app_profile_query, "
    "ram_query, disk_query, restart_safety, disk_forecast, pressure_forecast, "
    "install_impact, workload_analysis, trend_analysis"
)

_SYSTEM_PROMPT = (
    "You are a precise tool-selection assistant for a macOS machine state monitor. "
    "Respond only with the JSON object as instructed. No prose, no markdown, no thinking."
)


def _build_selector_prompt(query: str) -> str:
    return (
        f"Given the user's question, select which monitoring tools to call.\n\n"
        f"Available tools:\n{_TOOL_LISTING}\n\n"
        f"Return a JSON object only — no markdown, no backticks:\n"
        f'{{"intent": "<known_intent_or_llm_selected>", '
        f'"tools": [{{"name": "<tool_name>", "arguments": {{}}}}]}}\n\n'
        f"Rules:\n"
        f"- Only use tool names from the list above\n"
        f"- Only include argument keys you want set to non-default values (or required args)\n"
        f"- Select 1 to 4 tools\n"
        f"- For intent, choose the closest from: {_KNOWN_INTENTS}\n"
        f"  or use 'llm_selected' if none fit\n"
        f"- If the question names a specific app, pass it as the 'name' argument to get_app_profile\n\n"
        f"User question: {query}"
    )


# ── JSON extraction ────────────────────────────────────────────────────────────

def _parse_json_response(text: str) -> dict[str, Any]:
    """Extract JSON from LLM response, stripping markdown fences if present."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fenced:
        text = fenced.group(1).strip()
    return json.loads(text)


# ── Public interface ───────────────────────────────────────────────────────────

def select_tools(query: str, provider: LLMProvider) -> Intent:
    """Use the LLM to select and validate tools for the given query.

    Makes one LLM call to select tools, validates every tool name and argument
    against the contract registry, then returns a structured Intent.

    Falls back to deterministic detect_intent() if:
    - The LLM call fails or times out
    - The response is not valid JSON
    - Any selected tool name is not in TOOL_REGISTRY
    - Any argument fails validate_arguments()
    - No tools were selected
    """
    try:
        response = provider.complete(
            system_prompt=_SYSTEM_PROMPT,
            user_message=_build_selector_prompt(query),
        )
        raw = _parse_json_response(response.text)
    except Exception:
        return detect_intent(query)

    if not isinstance(raw, dict) or "tools" not in raw or not isinstance(raw["tools"], list):
        return detect_intent(query)

    intent_name: str = raw.get("intent", "llm_selected")
    if not isinstance(intent_name, str) or not intent_name.strip():
        intent_name = "llm_selected"

    tools: list[str] = []
    parameters: dict[str, Any] = {}

    for entry in raw["tools"]:
        if not isinstance(entry, dict):
            return detect_intent(query)

        name = entry.get("name", "")
        if not isinstance(name, str) or name not in TOOL_REGISTRY:
            return detect_intent(query)

        args = entry.get("arguments", {})
        if not isinstance(args, dict):
            args = {}

        validation = validate_arguments(name, args)
        if not validation.valid:
            return detect_intent(query)

        tools.append(name)
        parameters[name] = validation.coerced_args

    if not tools:
        return detect_intent(query)

    return Intent(
        name=intent_name,
        description=_DESCRIPTIONS.get(intent_name, f"LLM-selected tools for: {query}"),
        tools=tools,
        parameters=parameters,
    )
