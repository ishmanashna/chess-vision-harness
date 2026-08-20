"""Shared wording for the web agent board-text channel."""

from __future__ import annotations

BOARD_CHANNEL_NUDGE = (
    "Read both before every move or answer. The PNG is the picture of the live board; "
    "board.txt is the same position as eight compact rows. Use the text grid to confirm "
    "every occupied square so you play this board, not a remembered opening. Last-move "
    "highlights on the PNG are not extra pieces. Do not skip board.txt."
)

_WHITE_BOTTOM_LEGEND = (
    "The response is the live position as eight compact rows, ranks 8 through 1. "
    "The header row lists file letters left to right, matching the PNG (a through h "
    "for ladder games). White=uppercase, Black=lowercase, and .=empty. "
    "Those file columns are correct — use them to read each square."
)

_MOVING_SIDE_LEGEND = (
    "The response is the live position as eight compact rows. The header row lists "
    "file letters left to right exactly as on the PNG (often h through a when Black "
    "is at the bottom). The side to move sits at the bottom of the image. Square "
    "names are absolute (a1 is still a1 on the board). White=uppercase, "
    "Black=lowercase, and .=empty. Those file columns are correct — match them to "
    "the image; do not treat them as unreliable."
)

_POSITION_SOURCE_BAN = (
    "Never use FEN, JSON metadata, move lists, files, chat, engines, or scripts "
    "as a position source."
)


def render_board_text_channel(
    url: str, auth: str, *, moving_side_at_bottom: bool = False
) -> str:
    """GET block for an authenticated board.txt URL (games, puzzles, or identify)."""
    legend = _MOVING_SIDE_LEGEND if moving_side_at_bottom else _WHITE_BOTTOM_LEGEND
    return f"""GET {url}
Header: {auth}
{legend}
Authenticated board.txt is always allowed — same live position as the PNG.
{BOARD_CHANNEL_NUDGE}
{_POSITION_SOURCE_BAN}"""


def render_board_text_access(base_url: str, game_id: str, auth: str) -> str:
    url = f"{base_url.rstrip('/')}/api/v1/games/{game_id}/board.txt"
    return render_board_text_channel(url, auth)


def render_board_text_access_only(base_url: str, game_id: str, auth: str) -> str:
    """Text-only agents: board.txt is the sole position channel."""
    url = f"{base_url.rstrip('/')}/api/v1/games/{game_id}/board.txt"
    return f"""   - GET {url}
     Header: {auth}
{_WHITE_BOTTOM_LEGEND}
This authenticated board.txt is your position source — read it every turn before you move.
{_POSITION_SOURCE_BAN}"""
