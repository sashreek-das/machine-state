"""Semantic runtime layer — Phase 5.

Translates raw machine metrics into operating-system-level understanding:
applications, storage semantics, capabilities, pressure states, activity patterns.
"""

from . import applications, storage, capabilities, pressure, activity

__all__ = ["applications", "storage", "capabilities", "pressure", "activity"]
