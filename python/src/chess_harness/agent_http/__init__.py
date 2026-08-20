"""Headless HTTP client for /api/v1 AvE, puzzle, and identify play."""

from .client import AgentHttpClient, AgentHttpError, DEFAULT_USER_AGENT
from .queue import QueueEntry, default_queue_path, load_queue, reconcile_queue, save_queue
from .transport import TransportFn, urllib_transport

__all__ = [
    "AgentHttpClient",
    "AgentHttpError",
    "DEFAULT_USER_AGENT",
    "QueueEntry",
    "TransportFn",
    "default_queue_path",
    "load_queue",
    "reconcile_queue",
    "save_queue",
    "urllib_transport",
]
