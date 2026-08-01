"""Game type constants for harness play modes."""

from __future__ import annotations

from typing import Any, Dict

DEFAULT_GAME_TYPE = "agent_vs_engine"
GAME_TYPE_AGENT_VS_AGENT = "agent_vs_agent"
GAME_TYPE_HUMAN_VS_AGENT = "human_vs_agent"

__all__ = [
    "DEFAULT_GAME_TYPE",
    "GAME_TYPE_AGENT_VS_AGENT",
    "GAME_TYPE_HUMAN_VS_AGENT",
    "is_human_vs_agent_state",
    "is_unrated_result_row",
]


def is_human_vs_agent_state(state: dict) -> bool:
    return state.get("game_type") == GAME_TYPE_HUMAN_VS_AGENT


def is_unrated_result_row(result: Dict[str, Any]) -> bool:
    """True if a results.jsonl row must not affect Elo / rated game counts.

    Explicit ``rated: false`` is unrated. Missing ``rated`` means rated
    (backward compatible), except same-model AvA rows where
    ``model_name == opponent_model`` (covers historical rows without the flag).
    AvH exclusion stays separate via ``game_type``.
    """
    if result.get("rated") is False:
        return True
    model = result.get("model_name")
    opponent = result.get("opponent_model")
    if (
        result.get("game_type") == GAME_TYPE_AGENT_VS_AGENT
        and model
        and opponent
        and model == opponent
    ):
        return True
    return False
