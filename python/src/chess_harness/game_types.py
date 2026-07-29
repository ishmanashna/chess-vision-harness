"""Game type constants for harness play modes."""

DEFAULT_GAME_TYPE = "agent_vs_engine"
GAME_TYPE_AGENT_VS_AGENT = "agent_vs_agent"
GAME_TYPE_HUMAN_VS_AGENT = "human_vs_agent"

__all__ = [
    "DEFAULT_GAME_TYPE",
    "GAME_TYPE_AGENT_VS_AGENT",
    "GAME_TYPE_HUMAN_VS_AGENT",
    "is_human_vs_agent_state",
]


def is_human_vs_agent_state(state: dict) -> bool:
    return state.get("game_type") == GAME_TYPE_HUMAN_VS_AGENT
