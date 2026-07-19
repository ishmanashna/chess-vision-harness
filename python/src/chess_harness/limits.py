"""Abuse limits and idle timeout — read from environment with locked defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["HarnessLimits", "load_limits"]


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


@dataclass(frozen=True)
class HarnessLimits:
    max_concurrent_games: int = 10
    max_engine_processes: int = 12
    max_games_per_hour_per_key: int = 20
    max_moves_per_hour_per_key: int = 600
    idle_timeout_sec: int = 300
    max_agent_registrations_per_ip_per_hour: int = 10


def load_limits() -> HarnessLimits:
    """Load limits from env; defaults match docs/PUBLIC_AGENT_API_PLAN.md."""
    return HarnessLimits(
        max_concurrent_games=_int_env("CHESS_HARNESS_MAX_CONCURRENT_GAMES", 10),
        max_engine_processes=_int_env("CHESS_HARNESS_MAX_ENGINE_PROCESSES", 12),
        max_games_per_hour_per_key=_int_env("CHESS_HARNESS_MAX_GAMES_PER_HOUR_PER_KEY", 20),
        max_moves_per_hour_per_key=_int_env("CHESS_HARNESS_MAX_MOVES_PER_HOUR_PER_KEY", 600),
        idle_timeout_sec=_int_env("CHESS_HARNESS_IDLE_TIMEOUT_SEC", 300, minimum=60),
        max_agent_registrations_per_ip_per_hour=_int_env(
            "CHESS_HARNESS_MAX_AGENT_REGISTRATIONS_PER_IP_PER_HOUR", 10
        ),
    )
