"""Conversational LLM Layer (Phase 7).

The runtime computes truth. The LLM explains truth.

The LLM never:
  - inspects raw snapshots
  - computes metrics
  - invents system state

It only explains what the deterministic runtime has already computed.
"""
