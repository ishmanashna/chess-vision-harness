"""Lobby matchmaking helpers used by lobbies_api."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from .activity_audit import record_activity
from .agent_brief import public_base_url, render_agent_brief_avaa
from .api_limits import ApiLimitEnforcer, AuthContext, client_ip
from .avaa import participant_color
from .game_ids import new_game_id
from .game_service import GameService
from .game_types import GAME_TYPE_AGENT_VS_AGENT
from .lobby import ELO_BAND, LobbyStore, assign_colors


def public_waiting_row(lob: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "lobby_id": lob.get("lobby_id"),
        "host_display_name": lob.get("host_display_name"),
        "host_elo": lob.get("host_elo"),
        "created": lob.get("created"),
    }


def avaa_brief(
    svc: GameService, game_id: str, raw_key: str, model_id: str
) -> Optional[str]:
    state = svc.game_manager.load_state(game_id) or {}
    caller_color = participant_color(state, model_id)
    if not caller_color or not raw_key:
        return None
    opponent = (
        state.get("black_display_name")
        if caller_color == "WHITE"
        else state.get("white_display_name")
    ) or "Opponent"
    return render_agent_brief_avaa(
        public_base_url(),
        game_id,
        raw_key,
        caller_color.lower(),
        str(opponent),
    )


def match_payload(
    svc: GameService, game_id: str, model_id: str, raw_key: str
) -> Dict[str, Any]:
    state = svc.game_manager.load_state(game_id) or {}
    caller_color = participant_color(state, model_id)
    payload: Dict[str, Any] = {
        "ok": True,
        "status": "matched",
        "game_id": game_id,
    }
    if caller_color:
        payload["your_color"] = caller_color
        payload["your_turn"] = caller_color == "WHITE"
    brief = avaa_brief(svc, game_id, raw_key, model_id)
    if brief:
        payload["agent_brief"] = brief
    return payload


def try_match_lobby(
    lob: Dict[str, Any],
    joiner_model_id: str,
    joiner_elo: int,
    auth: AuthContext,
    raw_key: str,
    request: Request,
    *,
    svc: GameService,
    limits: ApiLimitEnforcer,
    lobby_store: LobbyStore,
    err: Callable[[int, str], JSONResponse],
) -> JSONResponse | Dict[str, Any]:
    if lob.get("host_model_id") == joiner_model_id:
        return err(400, "Cannot join your own lobby")
    host_elo = int(lob.get("host_elo") or 0)
    if abs(host_elo - joiner_elo) > ELO_BAND:
        return err(400, f"No lobby within ±{ELO_BAND} Elo")
    if lob.get("status") != "waiting":
        return err(409, "Lobby is no longer waiting")

    denied = limits.check_create_game(svc, auth)
    if denied:
        return denied

    colors = assign_colors(str(lob["host_model_id"]), joiner_model_id)
    game_id = new_game_id()
    result = svc.new_agent_vs_agent_game(
        game_id,
        colors["white_model_id"],
        colors["black_model_id"],
    )
    if not result.get("ok"):
        return err(400, result.get("error", "Failed to create game"))

    matched = lobby_store.mark_matched(
        str(lob["lobby_id"]),
        game_id=str(result.get("game_id") or game_id),
        white_model_id=colors["white_model_id"],
        black_model_id=colors["black_model_id"],
    )
    if matched is None:
        return err(409, "Lobby was matched by another player")

    limits.record_create_game(auth)
    try:
        record_activity(
            "create_game",
            model_id=joiner_model_id,
            game_id=str(result.get("game_id") or game_id),
            game_type=GAME_TYPE_AGENT_VS_AGENT,
            white_model_id=colors["white_model_id"],
            black_model_id=colors["black_model_id"],
            client_ip=client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )
    except Exception:
        pass
    return match_payload(svc, str(result.get("game_id") or game_id), joiner_model_id, raw_key)
