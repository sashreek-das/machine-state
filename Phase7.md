 # Phase 7 — Conversational LLM Layer

## Objective

Introduce natural language interaction over the deterministic runtime.

The LLM should:

* understand intent
* orchestrate semantic tools
* explain deterministic outputs
* communicate machine state conversationally

The LLM should NOT:

* compute truth
* invent system state
* replace deterministic logic

---

# Core Principle

The runtime computes truth.

The LLM explains truth.

---

# Architecture

```text
Machine Runtime
→ Structured Semantic Outputs
→ LLM Context Injection
→ Conversational Response
→ Human
```

---

# Supported LLM Providers

The architecture should support:

* OpenAI
* Anthropic
* Gemini
* Ollama
* Local GGUF models

Through a provider abstraction layer.

---

# New Components

## llm/

```text
llm/
  providers/
    openai.py
    anthropic.py
    gemini.py
    ollama.py

  prompts/
    explain_state.txt
    pressure_analysis.txt
    compatibility_check.txt

  orchestrator.py
  context_builder.py
```

---

# Required Features

## Context Builder

The runtime should provide:

* structured summaries
* semantic entities
* historical evidence
* pressure analysis
* capability outputs

The LLM should never inspect raw snapshots directly.

---

## Prompt Guardrails

Prompts must enforce:

* no hallucination
* no fabricated metrics
* evidence-backed explanations only
* deterministic runtime authority

---

## Conversational Queries

Examples:

```text
Why is my machine slow?
```

```text
Can I install this game?
```

```text
What changed since yesterday?
```

```text
What is consuming most memory?
```

---

## Explanation Layer

Translate:

```json
{
  "ramPressure": "critical",
  "topContributor": "Chrome"
}
```

Into:

```text
Your machine is under sustained memory pressure, and Chrome is currently the biggest contributor.
```

---

# Deliverables

* Multi-provider LLM abstraction
* Conversational orchestration
* Prompt framework
* Context builder
* Human-readable explanations
* Semantic runtime integration

---

# End State

The system should feel like:

* talking directly to the machine
* with awareness of its own state
* history
* capabilities
* limitations