"""query subpackage — deterministic query layer.

Public surface: answer_query().  Everything else is internal.
"""

from .router import answer_query

__all__ = ["answer_query"]
