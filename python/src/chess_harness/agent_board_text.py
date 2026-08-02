"""Shared wording for the web agent board-text fallback."""

from __future__ import annotations


def render_board_text_fallback(base_url: str, game_id: str, auth: str) -> str:
    url = f"{base_url.rstrip('/')}/api/v1/games/{game_id}/board.txt"
    return f"""Image fallback (only if the PNG is unavailable or unreadable):
GET {url}
Header: {auth}
The response is the live position as eight compact rows, ranks 8 through 1, with files a through h left to right. White=uppercase, Black=lowercase, and .=empty. It is absolute and white-at-bottom.
Use this sanctioned text fallback immediately before a move. Never use FEN, JSON metadata, move lists, files, chat, engines, or scripts as a position source."""
