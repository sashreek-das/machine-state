"""Background snapshot scheduler — continuous local machine awareness."""

from .daemon import start_daemon, stop_daemon, get_status
from .config import SchedulerConfig

__all__ = ["start_daemon", "stop_daemon", "get_status", "SchedulerConfig"]
