"""Shared wording for the web agent board-text channel."""

from __future__ import annotations

BOARD_CHANNEL_NUDGE = (
    "Read both before every move or answer. The PNG is the picture of the live board; "
    "board.txt is the same position as eight compact rows. Use the text grid to confirm "
    "every occupied square so you play this board, not a remembered opening. Last-move "
    "highlights on the PNG are not extra pieces. Do not skip board.txt."
)

_BOARD_TEXT_LEGEND = (
    "The response is the live position as eight compact rows, ranks 8 through 1, "
    "with files a through h left to right. White=uppercase, Black=lowercase, and .=empty. "
    "It is absolute and white-at-bottom."
)

_POSITION_SOURCE_BAN = (
    "Never use FEN, JSON metadata, move lists, files, chat, engines, or scripts "
    "as a position source."
)


def render_board_text_channel(url: str, auth: str) -> str:
    """GET block for an authenticated board.txt URL (games, puzzles, or identify)."""
    return f"""GET {url}
Header: {auth}
{_BOARD_TEXT_LEGEND}
Authenticated board.txt is always allowed — same live position as the PNG.
{BOARD_CHANNEL_NUDGE}
{_POSITION_SOURCE_BAN}"""


def render_board_text_access(base_url: str, game_id: str, auth: str) -> str:
    url = f"{base_url.rstrip('/')}/api/v1/games/{game_id}/board.txt"
    return render_board_text_channel(url, auth)
