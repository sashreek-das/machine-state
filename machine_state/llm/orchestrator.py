"""LLM orchestrator.

Coordinates the full pipeline:
  1. Run the planner (deterministic — computes truth)
  2. Build context (transforms structured results into LLM-readable text)
  3. Load the appropriate system prompt (enforces anti-hallucination rules)
  4. Call the LLM provider (explains truth)
  5. Return the conversational response

The LLM never sees raw snapshots, raw bytes, or internal IDs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..planner.planner import ExecutionPlan, PlanResult, ToolCall, execute_plan
from ..planner.contracts import TOOL_REGISTRY
from .context_builder import build_context
from .providers.base import LLMProvider, LLMResponse

_PROMPTS_DIR = Path(__file__).parent / "prompts"


# ── Prompt selection ───────────────────────────────────────────────────────────

_INTENT_TO_PROMPT: dict[str, str] = {
    "slowdown_analysis": "pressure_analysis.txt",
    "pressure_analysis": "pressure_analysis.txt",
    "restart_safety": "pressure_analysis.txt",
    "install_feasibility": "compatibility_check.txt",
    "compatibility_check": "compatibility_check.txt",
    # Phase 8
    "disk_forecast": "forecasting.txt",
    "pressure_forecast": "forecasting.txt",
    "install_impact": "forecasting.txt",
    "workload_analysis": "forecasting.txt",
    "trend_analysis": "forecasting.txt",
}


def _load_prompt(intent: str) -> str:
    """Load the system prompt appropriate for this intent."""
    prompt_file = _INTENT_TO_PROMPT.get(intent, "explain_state.txt")
    prompt_path = _PROMPTS_DIR / prompt_file
    try:
        return prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return (_PROMPTS_DIR / "explain_state.txt").read_text(encoding="utf-8").strip()


# ── Main orchestration ─────────────────────────────────────────────────────────

def explain(
    query: str,
    snapshot: dict[str, Any],
    recent_snapshots: list[dict[str, Any]],
    db_path: str,
    provider: LLMProvider,
) -> dict[str, Any]:
    """Full pipeline: query → plan → context → LLM → conversational response.

    Returns a dict with:
      - response: the natural language answer
      - intent: detected intent
      - provider: LLM provider name
      - model: LLM model used
      - tokens: token usage (if available)
      - context: the structured context passed to the LLM
      - plan_status: whether the runtime plan succeeded
    """
    # 1. Select tools via LLM, fall back to regex on any failure
    from ..planner.llm_selector import select_tools
    intent = select_tools(query, provider)
    steps = [
        ToolCall(tool_name=t, arguments=intent.parameters.get(t, {}))
        for t in intent.tools
        if t in TOOL_REGISTRY
    ]
    plan = ExecutionPlan(
        intent=intent.name,
        intent_description=intent.description,
        query=query,
        steps=steps,
    )
    plan_result = execute_plan(plan, snapshot, recent_snapshots, db_path)

    if plan_result.intent == "unknown" or not plan_result.aggregated:
        return {
            "response": (
                "I don't have enough runtime data to answer that question confidently. "
                "Try a more specific question about your machine's RAM, disk, or running applications."
            ),
            "intent": "unknown",
            "provider": provider.provider_name,
            "model": provider.model_name,
            "plan_status": "unknown",
        }

    # 2. Build structured context
    context = build_context(plan_result.intent, plan_result.aggregated)

    # 3. Load system prompt
    system_prompt = _load_prompt(plan_result.intent)

    # 4. Build user message
    user_message = f"Question: {query}\n\n{context}"

    # 5. Call LLM
    llm_response: LLMResponse = provider.complete(system_prompt, user_message)

    return {
        "response": llm_response.text,
        "intent": plan_result.intent,
        "provider": llm_response.provider,
        "model": llm_response.model,
        "tokens": {
            "input": llm_response.input_tokens,
            "output": llm_response.output_tokens,
            "total": llm_response.total_tokens,
        },
        "context": context,
        "plan_status": plan_result.status,
        "runtime_data": plan_result.aggregated,
    }


def explain_from_plan_result(
    query: str,
    plan_result: PlanResult,
    provider: LLMProvider,
) -> dict[str, Any]:
    """Explain an already-executed plan result.

    Useful when the plan has already been run and you only need the LLM explanation.
    """
    if plan_result.intent == "unknown" or not plan_result.aggregated:
        return {
            "response": (
                "I don't have enough runtime data to answer that question. "
                "Try asking about RAM, disk space, or your running applications."
            ),
            "intent": "unknown",
            "provider": provider.provider_name,
            "model": provider.model_name,
        }

    context = build_context(plan_result.intent, plan_result.aggregated)
    system_prompt = _load_prompt(plan_result.intent)
    user_message = f"Question: {query}\n\n{context}"
    llm_response = provider.complete(system_prompt, user_message)

    return {
        "response": llm_response.text,
        "intent": plan_result.intent,
        "provider": llm_response.provider,
        "model": llm_response.model,
        "tokens": {
            "input": llm_response.input_tokens,
            "output": llm_response.output_tokens,
            "total": llm_response.total_tokens,
        },
        "context": context,
        "plan_status": plan_result.status,
    }
