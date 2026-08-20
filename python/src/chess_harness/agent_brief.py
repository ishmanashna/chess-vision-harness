"""Paste-ready agent prompt for remote HTTP play."""

from __future__ import annotations

from .agent_brief_common import public_base_url
from .agent_brief_text import (
    render_agent_brief as render_agent_brief_text,
    render_agent_brief_avaa as render_agent_brief_avaa_text,
    render_agent_brief_human as render_agent_brief_human_text,
)
from .agent_brief_vision import (
    render_agent_brief as render_agent_brief_vision,
    render_agent_brief_avaa as render_agent_brief_avaa_vision,
    render_agent_brief_human as render_agent_brief_human_vision,
)
from .models import OBSERVATION_TEXT, normalize_observation

__all__ = [
    "public_base_url",
    "render_agent_brief",
    "render_agent_brief_avaa",
    "render_agent_brief_human",
]


def render_agent_brief(
    base_url: str,
    game_id: str,
    api_key: str,
    *,
    observation: str = "vision",
) -> str:
    if normalize_observation(observation) == OBSERVATION_TEXT:
        return render_agent_brief_text(base_url, game_id, api_key)
    return render_agent_brief_vision(base_url, game_id, api_key)


def render_agent_brief_avaa(
    base_url: str,
    game_id: str,
    api_key: str,
    color: str,
    opponent_name: str,
    *,
    observation: str = "vision",
) -> str:
    if normalize_observation(observation) == OBSERVATION_TEXT:
        return render_agent_brief_avaa_text(
            base_url, game_id, api_key, color, opponent_name
        )
    return render_agent_brief_avaa_vision(
        base_url, game_id, api_key, color, opponent_name
    )


def render_agent_brief_human(
    base_url: str,
    game_id: str,
    api_key: str,
    color: str,
    human_nickname: str,
    *,
    observation: str = "vision",
) -> str:
    if normalize_observation(observation) == OBSERVATION_TEXT:
        return render_agent_brief_human_text(
            base_url, game_id, api_key, color, human_nickname
        )
    return render_agent_brief_human_vision(
        base_url, game_id, api_key, color, human_nickname
    )
