"""Parse occupied squares from harness board.txt (identify stub helper)."""

from __future__ import annotations

from typing import Dict


def pieces_from_board_text(board_text: str) -> Dict[str, str]:
    """Return occupied square -> piece code (wP/bK) from a board.txt grid."""
    lines = [line for line in board_text.splitlines() if line.strip()]
    if len(lines) < 2:
        return {}
    header = lines[0].strip()
    if header.startswith("h "):
        files = list("hgfedcba")
    else:
        files = list("abcdefgh")
    out: Dict[str, str] = {}
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        rank = parts[0]
        for index, symbol in enumerate(parts[1:]):
            if symbol == "." or index >= len(files):
                continue
            if symbol.isupper():
                out[files[index] + rank] = "w" + symbol.upper()
            else:
                out[files[index] + rank] = "b" + symbol.upper()
    return out
