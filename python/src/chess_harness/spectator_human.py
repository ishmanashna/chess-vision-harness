"""Spectator helpers for human-vs-agent games (no eval, display-only agent Elo)."""

from __future__ import annotations

from typing import Any, Dict

import chess

from .game_types import GAME_TYPE_HUMAN_VS_AGENT, is_human_vs_agent_state

__all__ = [
    "GAME_TYPE_HUMAN_VS_AGENT",
    "human_active_card",
    "human_display_names",
    "human_list_fields",
    "human_state_extra",
    "show_eval_for_state",
]


def show_eval_for_state(state: dict) -> bool:
    return not is_human_vs_agent_state(state)


def human_display_names(state: dict) -> tuple[str, str]:
    human = state.get("human_nickname") or "Human"
    agent = state.get("model_display_name") or state.get("model_name") or "Agent"
    if state.get("agent_color") == "WHITE":
        return agent, human
    return human, agent


def human_list_fields(state: dict, elo: Dict[str, Any]) -> Dict[str, Any]:
    white_name, black_name = human_display_names(state)
    agent_elo = elo.get("agent_elo")
    return {
        "game_type": GAME_TYPE_HUMAN_VS_AGENT,
        "human_nickname": state.get("human_nickname") or "Human",
        "human_color": state.get("human_color"),
        "agent_color": state.get("agent_color"),
        "white_display_name": white_name,
        "black_display_name": black_name,
        "model_id": state.get("model_name"),
        "model_name": state.get("model_display_name") or state.get("model_name") or "Agent",
        "agent_elo": agent_elo,
        "opponent_label": state.get("human_nickname") or "Human",
        "show_eval": False,
    }


def human_active_card(state: dict, game_id: str, board: chess.Board, elo: Dict[str, Any]) -> Dict[str, Any]:
    white_name, black_name = human_display_names(state)
    mover = white_name if board.turn == chess.WHITE else black_name
    turn = f"{mover} to move"
    if board.is_check():
        turn += " · check"
    agent_name = state.get("model_display_name") or state.get("model_name") or "Agent"
    return {
        "game_type": GAME_TYPE_HUMAN_VS_AGENT,
        "white_name": white_name,
        "black_name": black_name,
        "agent_name": agent_name,
        "opponent_label": state.get("human_nickname") or "Human",
        "human_nickname": state.get("human_nickname") or "Human",
        "agent_color": state.get("agent_color"),
        "agent_elo": elo.get("agent_elo"),
        "move_number": board.fullmove_number,
        "plies": len(state.get("moves", [])),
        "turn_label": turn,
        "eval_white_cp": None,
        "eval_ui": None,
        "show_eval": False,
        "board_url": f"/g/{game_id}/board.png",
        "board_cache": f"{len(state.get('moves', []))}:{state.get('last_move_uci') or ''}",
    }


def human_state_extra(state: dict, elo_ctx: Dict[str, Any]) -> Dict[str, Any]:
    return human_list_fields(state, elo_ctx)
