"""In-memory abuse limits for /api/v1 — sliding windows + concurrent caps."""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import shutil
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from .game_service import GameService
from .limits import HarnessLimits, load_limits
from .paths import resolve_base_dir

__all__ = [
    "ApiLimitEnforcer",
    "AuthContext",
    "PUBLIC_BY_KEY_LIMIT_PER_IP_PER_HOUR",
    "limit_error",
    "client_ip",
    "key_fingerprint",
    "get_limit_enforcer",
]

_log = logging.getLogger(__name__)

_shared_enforcer: Optional["ApiLimitEnforcer"] = None
_misconfigured_proxy_warned = False


def key_fingerprint(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()[:16]


def get_limit_enforcer() -> "ApiLimitEnforcer":
    """Process-wide enforcer so Create Game and /api/v1 share counters."""
    global _shared_enforcer
    if _shared_enforcer is None:
        _shared_enforcer = ApiLimitEnforcer()
    return _shared_enforcer


_WINDOW_SEC = 3600.0

# Per-(client ip, fingerprint) cap on public attempts-list scans driven by the
# ``by_key`` (attempt chain) filter: enough for watch-page auto-follow cadence
# (a few requests per minute) while stopping unbounded key-scanning loops.
PUBLIC_BY_KEY_LIMIT_PER_IP_PER_HOUR = 600


def _trusted_proxy_networks() -> list[ipaddress._BaseNetwork]:
    raw = os.environ.get("CHESS_HARNESS_TRUSTED_PROXIES", "")
    networks: list[ipaddress._BaseNetwork] = []
    for value in raw.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks


def _peer_is_trusted(request: Request) -> bool:
    peer = request.client.host if request.client else ""
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(address in network for network in _trusted_proxy_networks())


def _parse_ip_header(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    candidate = value.split(",")[0].strip()
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def _trusted_proxies_configured() -> bool:
    return bool(os.environ.get("CHESS_HARNESS_TRUSTED_PROXIES", "").strip())


def _is_loopback_peer(peer: str) -> bool:
    try:
        return ipaddress.ip_address(peer).is_loopback
    except ValueError:
        return False


def _has_forwarded_identity_header(request: Request) -> bool:
    for header in ("x-forwarded-for", "cf-connecting-ip"):
        value = request.headers.get(header)
        if value and value.strip():
            return True
    return False


def _maybe_warn_misconfigured_trusted_proxies(request: Request) -> None:
    """Log once when Online-style proxy headers arrive but trust is unset."""
    global _misconfigured_proxy_warned
    if _misconfigured_proxy_warned or _trusted_proxies_configured():
        return
    peer = request.client.host if request.client and request.client.host else ""
    if not _is_loopback_peer(peer) or not _has_forwarded_identity_header(request):
        return
    _misconfigured_proxy_warned = True
    _log.warning(
        "CHESS_HARNESS_TRUSTED_PROXIES is unset but the request peer is loopback (%s) "
        "and carries X-Forwarded-For or CF-Connecting-IP. All visitors will share the "
        "peer IP for rate limits. For Pages/cloudflared Online deploys set "
        "CHESS_HARNESS_TRUSTED_PROXIES=127.0.0.0/8 (trust is never enabled without this config).",
        peer,
    )


def reset_trusted_proxy_warning_for_tests() -> None:
    """Clear the one-shot misconfiguration warning (tests only)."""
    global _misconfigured_proxy_warned
    _misconfigured_proxy_warned = False


def client_ip(request: Request) -> str:
    _maybe_warn_misconfigured_trusted_proxies(request)
    peer = request.client.host if request.client and request.client.host else "unknown"
    if not _peer_is_trusted(request):
        return peer
    for header in ("x-forwarded-for", "cf-connecting-ip"):
        parsed = _parse_ip_header(request.headers.get(header))
        if parsed:
            return parsed
    return peer


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
    scoped: Optional[Dict[str, Any]] = None


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
        self._imagines_by_key = _SlidingWindow()
        self._registrations_by_ip = _SlidingWindow()
        self._public_by_key_by_ip = _SlidingWindow()

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

    def check_imagine(self, auth: AuthContext) -> Optional[JSONResponse]:
        lim = self.limits()
        fp = auth.key_fingerprint
        if self._imagines_by_key.count(fp) >= lim.max_imagines_per_hour_per_key:
            return limit_error(
                429,
                f"API key imagine limit exceeded ({lim.max_imagines_per_hour_per_key}/hour)",
                self._imagines_by_key.retry_after(fp, lim.max_imagines_per_hour_per_key),
            )
        return None

    def record_imagine(self, auth: AuthContext) -> None:
        self._imagines_by_key.add(auth.key_fingerprint)

    def check_puzzle_attempt(
        self, active_count: int, auth: AuthContext
    ) -> Optional[JSONResponse]:
        """Operator-tunable concurrency cap for puzzle attempts per key.

        Puzzle attempts are not games: they never count against the game or
        move caps. This dedicated cap bounds concurrent attempts only —
        "unlimited" means no rating cap, not unbounded concurrency.
        """
        lim = self.limits()
        if active_count >= lim.max_puzzle_attempts_per_key:
            return limit_error(
                429,
                f"Puzzle attempt concurrency limit reached ({lim.max_puzzle_attempts_per_key}); finish or abandon an active attempt first",
                60,
            )
        return None

    def check_public_by_key(
        self, request: Request, fingerprint: str
    ) -> Optional[JSONResponse]:
        """Per-IP+key sliding window on public ``by_key`` attempt-chain scans."""
        window_key = f"{client_ip(request)}:{fingerprint}"
        if (
            self._public_by_key_by_ip.count(window_key)
            >= PUBLIC_BY_KEY_LIMIT_PER_IP_PER_HOUR
        ):
            return limit_error(
                429,
                "Too many attempt-chain lookups from this client; try again later",
                self._public_by_key_by_ip.retry_after(
                    window_key, PUBLIC_BY_KEY_LIMIT_PER_IP_PER_HOUR
                ),
            )
        return None

    def record_public_by_key(self, request: Request, fingerprint: str) -> None:
        self._public_by_key_by_ip.add(f"{client_ip(request)}:{fingerprint}")

    def check_identify_attempt(
        self, active_count: int, auth: AuthContext
    ) -> Optional[JSONResponse]:
        """Operator-tunable concurrency cap for board-identification attempts.

        Board-identification attempts are not games and never count against the
        game or move caps. This dedicated cap bounds concurrent attempts only —
        "unlimited" means no rating cap, not unbounded concurrency.
        """
        lim = self.limits()
        if active_count >= lim.max_identify_attempts_per_key:
            return limit_error(
                429,
                f"Identify attempt concurrency limit reached ({lim.max_identify_attempts_per_key}); finish or abandon an active attempt first",
                60,
            )
        return None

    def reset_counters(self) -> None:
        """Clear sliding windows (tests / process restart semantics)."""
        self._games_by_key = _SlidingWindow()
        self._moves_by_key = _SlidingWindow()
        self._imagines_by_key = _SlidingWindow()
        self._registrations_by_ip = _SlidingWindow()
        self._public_by_key_by_ip = _SlidingWindow()

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
                "max_imagines_per_hour_per_key": lim.max_imagines_per_hour_per_key,
                "max_puzzle_attempts_per_key": lim.max_puzzle_attempts_per_key,
                "max_identify_attempts_per_key": lim.max_identify_attempts_per_key,
                "idle_timeout_sec": lim.idle_timeout_sec,
            },
            "engine_count_note": (
                "Opponent pools are trimmed to CHESS_HARNESS_MAX_ENGINE_PROCESSES; "
                "count is live pooled adapters plus move/eval engines"
            ),
        }
