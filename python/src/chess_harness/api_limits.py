"""In-memory abuse limits for /api/v1 — sliding windows + concurrent caps."""

from __future__ import annotations

import hashlib
import shutil
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Deque, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from .game_service import GameService
from .limits import HarnessLimits, load_limits
from .paths import resolve_base_dir

__all__ = [
    "ApiLimitEnforcer",
    "AuthContext",
    "limit_error",
    "client_ip",
    "key_fingerprint",
    "get_limit_enforcer",
]

_shared_enforcer: Optional["ApiLimitEnforcer"] = None


def key_fingerprint(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()[:16]


def get_limit_enforcer() -> "ApiLimitEnforcer":
    """Process-wide enforcer so Create Game and /api/v1 share counters."""
    global _shared_enforcer
    if _shared_enforcer is None:
        _shared_enforcer = ApiLimitEnforcer()
    return _shared_enforcer


_WINDOW_SEC = 3600.0


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def limit_error(status: int, message: str, retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"ok": False, "error": message},
        headers={"Retry-After": str(max(1, retry_after))},
    )


@dataclass(frozen=True)
class AuthContext:
    model_id: str
    key_fingerprint: str


class _SlidingWindow:
    def __init__(self, window_sec: float = _WINDOW_SEC) -> None:
        self.window_sec = window_sec
        self._events: Dict[str, Deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> Deque[float]:
        q = self._events[key]
        cutoff = now - self.window_sec
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    def count(self, key: str) -> int:
        return len(self._prune(key, time.time()))

    def add(self, key: str) -> None:
        now = time.time()
        self._prune(key, now).append(now)

    def retry_after(self, key: str, limit: int) -> int:
        q = self._prune(key, time.time())
        if len(q) < limit:
            return 1
        return max(1, int(q[0] + self.window_sec - time.time()) + 1)


def _active_game_count(game_service: GameService) -> int:
    return len(game_service.game_manager.list_games(status_filter="in_progress"))


def _live_engine_count(game_service: GameService) -> int:
    ctrl = game_service.controller
    count = ctrl.opponent_mgr.live_adapter_count()
    if ctrl._eval_engine is not None:
        count += 1
    return count


def _waiting_lobby_count() -> int:
    from .lobby import LobbyStore

    try:
        return len(LobbyStore().list_waiting())
    except OSError:
        return 0


def _active_agent_vs_agent_count(game_service: GameService) -> int:
    from .game_types import GAME_TYPE_AGENT_VS_AGENT

    return sum(
        1
        for game in game_service.game_manager.list_games(status_filter="in_progress")
        if (game.get("state") or {}).get("game_type") == GAME_TYPE_AGENT_VS_AGENT
    )


def _active_human_vs_agent_count(game_service: GameService) -> int:
    from .game_types import GAME_TYPE_HUMAN_VS_AGENT

    return sum(
        1
        for game in game_service.game_manager.list_games(status_filter="in_progress")
        if (game.get("state") or {}).get("game_type") == GAME_TYPE_HUMAN_VS_AGENT
    )


class ApiLimitEnforcer:
    """Process-local counters; resets on restart."""

    def __init__(
        self,
        limits: Optional[HarnessLimits] = None,
        *,
        get_limits: Optional[Callable[[], HarnessLimits]] = None,
    ):
        self._get_limits = get_limits or load_limits
        self._limits = limits
        self._games_by_key = _SlidingWindow()
        self._moves_by_key = _SlidingWindow()
        self._registrations_by_ip = _SlidingWindow()

    def limits(self) -> HarnessLimits:
        return self._limits if self._limits is not None else self._get_limits()

    def check_register_agent(self, request: Request) -> Optional[JSONResponse]:
        lim = self.limits()
        ip = client_ip(request)
        if self._registrations_by_ip.count(ip) >= lim.max_agent_registrations_per_ip_per_hour:
            return limit_error(
                429,
                "Too many agent registrations from this IP; try again later",
                self._registrations_by_ip.retry_after(ip, lim.max_agent_registrations_per_ip_per_hour),
            )
        return None

    def record_register_agent(self, request: Request) -> None:
        self._registrations_by_ip.add(client_ip(request))

    def check_create_game(
        self, game_service: GameService, auth: AuthContext
    ) -> Optional[JSONResponse]:
        lim = self.limits()
        active = _active_game_count(game_service)
        if active >= lim.max_concurrent_games:
            return limit_error(
                503,
                f"Server at concurrent game capacity ({lim.max_concurrent_games})",
                60,
            )
        engines = _live_engine_count(game_service)
        if engines >= lim.max_engine_processes:
            return limit_error(
                503,
                f"Server at engine process capacity ({lim.max_engine_processes})",
                30,
            )
        fp = auth.key_fingerprint
        if self._games_by_key.count(fp) >= lim.max_games_per_hour_per_key:
            return limit_error(
                429,
                f"API key game limit exceeded ({lim.max_games_per_hour_per_key}/hour)",
                self._games_by_key.retry_after(fp, lim.max_games_per_hour_per_key),
            )
        return None

    def record_create_game(self, auth: AuthContext) -> None:
        self._games_by_key.add(auth.key_fingerprint)

    def check_move(
        self, game_service: GameService, auth: AuthContext
    ) -> Optional[JSONResponse]:
        lim = self.limits()
        fp = auth.key_fingerprint
        if self._moves_by_key.count(fp) >= lim.max_moves_per_hour_per_key:
            return limit_error(
                429,
                f"API key move limit exceeded ({lim.max_moves_per_hour_per_key}/hour)",
                self._moves_by_key.retry_after(fp, lim.max_moves_per_hour_per_key),
            )
        if _live_engine_count(game_service) >= lim.max_engine_processes:
            return limit_error(503, "Server at engine process capacity", 30)
        return None

    def record_move(self, auth: AuthContext) -> None:
        self._moves_by_key.add(auth.key_fingerprint)

    def reset_counters(self) -> None:
        """Clear sliding windows (tests / process restart semantics)."""
        self._games_by_key = _SlidingWindow()
        self._moves_by_key = _SlidingWindow()
        self._registrations_by_ip = _SlidingWindow()

    def metrics(self, game_service: GameService) -> Dict[str, object]:
        lim = self.limits()
        base = resolve_base_dir()
        try:
            disk = shutil.disk_usage(base)
            disk_free_bytes = disk.free
        except OSError:
            disk_free_bytes = None
        return {
            "active_games": _active_game_count(game_service),
            "active_agent_vs_agent": _active_agent_vs_agent_count(game_service),
            "active_human_vs_agent": _active_human_vs_agent_count(game_service),
            "engine_count": _live_engine_count(game_service),
            "waiting_lobbies": _waiting_lobby_count(),
            "disk_free_bytes": disk_free_bytes,
            "limits": {
                "max_concurrent_games": lim.max_concurrent_games,
                "max_engine_processes": lim.max_engine_processes,
                "max_games_per_hour_per_key": lim.max_games_per_hour_per_key,
                "max_moves_per_hour_per_key": lim.max_moves_per_hour_per_key,
                "idle_timeout_sec": lim.idle_timeout_sec,
            },
            "engine_count_note": (
                "Engines are released after each move; count reflects in-flight work only"
            ),
        }
