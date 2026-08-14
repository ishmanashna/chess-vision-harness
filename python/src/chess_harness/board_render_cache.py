"""Track which board PNG on disk matches the current game revision."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

_board_render_keys: Dict[str, str] = {}


def board_render_cache_key(state: Dict[str, Any]) -> str:
    return f"{len(state.get('moves', []))}:{state.get('last_move_uci') or ''}"


def note_board_rendered(game_id: str, state: Dict[str, Any]) -> None:
    _board_render_keys[game_id] = board_render_cache_key(state)


def board_png_is_fresh(game_id: str, state: Dict[str, Any], board_path: Path) -> bool:
    if not board_path.is_file():
        return False
    return _board_render_keys.get(game_id) == board_render_cache_key(state)
