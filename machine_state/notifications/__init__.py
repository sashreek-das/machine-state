"""Local notification layer — deterministic, evidence-backed, rate-limited."""

from .engine import evaluate_and_notify, send_notification, get_pending_notifications

__all__ = ["evaluate_and_notify", "send_notification", "get_pending_notifications"]
