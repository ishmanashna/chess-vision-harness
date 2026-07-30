"""Agent-safe API surfaces — no FEN, moves, or position leaks."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

_QUALITY_STATE_KEYS = (
    "quality_at",
    "quality_thin",
    "quality_depth",
    "white_accuracy",
    "black_accuracy",
    "white_play_rating",
    "black_play_rating",
    "agent_accuracy",
    "agent_play_rating",
)


def quality_fields_from_state(
    state: Dict[str, Any], *, include_provisional: bool = False
) -> Dict[str, Any]:
    """Estimated Elo + accuracy fields when quality analysis has run."""
    if (
        not include_provisional
        and state.get("quality_provisional")
        and state.get("status") == "in_progress"
    ):
        return {}
    return {key: state[key] for key in _QUALITY_STATE_KEYS if key in state}


def debug_state_enabled(debug_param: Optional[str] = None) -> bool:
    """Full internal state only when operator enables debug."""
    if debug_param == "1":
        return os.getenv("CHESS_HARNESS_DEBUG", "").lower() in ("1", "true", "yes")
    return False


def _agent_outcome(agent_color: str, result: Optional[str]) -> Dict[str, str]:
    from .board_controller import BoardController

    return BoardController.agent_outcome(agent_color, result or "")


def agent_safe_status(
    state: Dict[str, Any],
    board_path: str,
    persp: Dict[str, Any],
    *,
    caller_color: Optional[str] = None,
) -> Dict[str, Any]:
    """CLI/MCP status — metadata only, no position."""
    in_progress = state.get("status") == "in_progress"
    color = caller_color or persp.get("agent_color") or state.get("agent_color")
    response: Dict[str, Any] = {
        "ok": True,
        "game_id": state.get("game_id"),
        "result": state.get("result"),
        "move_count": len(state.get("moves", [])),
        "board_path": board_path,
        **persp,
    }
    if color:
        response["agent_color"] = color
    # Finished/abandoned games keep a live board FEN; trust harness status, not board.is_game_over().
    if not in_progress:
        response["game_over"] = True
        response["your_turn"] = False
        response["in_check"] = False
    if not in_progress and state.get("last_move_uci"):
        response["last_move"] = state["last_move_uci"]
    response.update(quality_fields_from_state(state))
    return response


def agent_safe_board(
    state: Dict[str, Any],
    board_path: str,
    persp: Dict[str, Any],
    *,
    caller_color: Optional[str] = None,
) -> Dict[str, Any]:
    color = caller_color or persp.get("agent_color") or state.get("agent_color")
    response: Dict[str, Any] = {
        "ok": True,
        "game_id": state.get("game_id"),
        "board_path": board_path,
    }
    if color:
        response["agent_color"] = color
    if state.get("status") != "in_progress" or state.get("result"):
        response["result"] = state.get("result")
        response["game_over"] = True
        if color:
            response.update(_agent_outcome(color, state.get("result")))
    else:
        response["your_turn"] = persp.get("your_turn", False)
        response["game_over"] = False
    return response


def agent_safe_spectator_state(
    state: Dict[str, Any],
    *,
    revision: str,
    summary: str,
    elo_change: str,
    end_reason_label: Optional[str],
    engine_label: str,
    agent_outcome: Optional[Dict[str, str]],
    eval_ui: Optional[Dict[str, Any]],
    agent_elo: Optional[int],
    engine_elo: Optional[int],
    game_over: bool,
    board_path: str,
    opponent_label: Optional[str] = None,
    show_eval: bool = True,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Public spectator API — no FEN or move list."""
    payload: Dict[str, Any] = {
        "game_id": state.get("game_id"),
        "revision": revision,
        "summary": summary,
        "status": state.get("status"),
        "game_type": state.get("game_type"),
        "agent_color": state.get("agent_color"),
        "your_turn": state.get("status") == "in_progress" and not game_over,
        "game_over": game_over,
        "result": state.get("result"),
        "move_count": len(state.get("moves", [])),
        "opponent_id": state.get("opponent_id"),
        "opponent_label": opponent_label or state.get("opponent_label"),
        "opponent_elo": state.get("opponent_elo"),
        "model_name": state.get("model_name"),
        "model_display_name": state.get("model_display_name"),
        "agent_elo": agent_elo,
        "engine_elo": engine_elo,
        "engine_label": engine_label,
        "elo_change": elo_change,
        "end_reason_label": end_reason_label,
        "agent_outcome": agent_outcome,
        "eval_ui": eval_ui,
        "show_eval": show_eval,
        "board_path": board_path,
        "board_url": f"/g/{state.get('game_id')}/board.png",
    }
    if extra:
        payload.update(extra)
    payload.update(quality_fields_from_state(state, include_provisional=True))
    return payload
