"""Agent-safe game list entries for GET /api/v1/games."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .avaa import is_avaa_state, participant_color
from .game_service import GameService
from .game_types import is_human_vs_agent_state
from .models import normalize_observation

__all__ = ["list_games_for_agent", "resolve_agent_caller_color"]


def agent_owns_game(
    state: Dict[str, Any], *, model_id: str, key_fingerprint: str
) -> bool:
    if is_avaa_state(state):
        return participant_color(state, model_id, key_fingerprint) is not None
    return state.get("model_name") == model_id


def resolve_agent_caller_color(
    state: Dict[str, Any], *, model_id: str, key_fingerprint: str
) -> Optional[str]:
    if is_avaa_state(state):
        return participant_color(state, model_id, key_fingerprint)
    if is_human_vs_agent_state(state):
        if model_id != state.get("model_name"):
            return None
        return state.get("agent_color", "WHITE")
    if state.get("model_name") != model_id:
        return None
    return state.get("agent_color", "WHITE")


def _list_entry_from_status(
    state: Dict[str, Any], status_payload: Dict[str, Any]
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "game_id": state.get("game_id"),
        "status": state.get("status"),
        "observation": normalize_observation(state.get("observation")),
        "game_over": bool(status_payload.get("game_over")),
        "your_turn": bool(status_payload.get("your_turn")),
    }
    if status_payload.get("agent_color"):
        entry["agent_color"] = status_payload["agent_color"]
    if status_payload.get("result") is not None:
        entry["result"] = status_payload["result"]
    return entry


def _list_entry_finished(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "game_id": state.get("game_id"),
        "status": state.get("status"),
        "observation": normalize_observation(state.get("observation")),
        "game_over": True,
        "your_turn": False,
        "result": state.get("result"),
    }


def list_games_for_agent(
    service: GameService,
    *,
    model_id: str,
    key_fingerprint: str,
    include_finished: bool = False,
    finished_limit: int = 20,
) -> List[Dict[str, Any]]:
    """In-progress games for this key; optionally recent finished."""
    service._prune_idle()
    entries: List[Dict[str, Any]] = []
    finished_seen = 0
    for item in service.game_manager.list_games():
        state = item["state"]
        game_id = item["game_id"]
        if not agent_owns_game(state, model_id=model_id, key_fingerprint=key_fingerprint):
            continue
        caller_color = resolve_agent_caller_color(
            state, model_id=model_id, key_fingerprint=key_fingerprint
        )
        if caller_color is None:
            continue
        if state.get("status") == "in_progress":
            status_payload = service.status(game_id, caller_color=caller_color)
            if not status_payload.get("ok"):
                continue
            entries.append(_list_entry_from_status(state, status_payload))
            continue
        if not include_finished or finished_seen >= finished_limit:
            continue
        entries.append(_list_entry_finished(state))
        finished_seen += 1
    return entries
