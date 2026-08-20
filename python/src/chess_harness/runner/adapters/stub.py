"""In-process stub move provider."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from .board_parse import pieces_from_board_text


_DEFAULT_WHITE = ("e2e4", "g1f3", "f1c4", "d1h5")
_DEFAULT_BLACK = ("e7e5", "b8c6", "g8f6")


class StubAdapter:
    provider = "stub"

    def __init__(self, moves: Sequence[str] | None = None):
        self._script = list(moves) if moves is not None else None
        self._index = 0

    @staticmethod
    def _side_to_move(board_text: str) -> str:
        for line in board_text.splitlines():
            if line.startswith("side_to_move:"):
                return line.split(":", 1)[1].strip().lower()
        return "white"

    def _default_move(self, board_text: str) -> str:
        side = self._side_to_move(board_text)
        book = _DEFAULT_WHITE if side == "white" else _DEFAULT_BLACK
        if self._index < len(book):
            move = book[self._index]
            self._index += 1
            return move
        return book[-1] if book else "e2e4"

    def choose_move(self, *, board_text: str, board_png: Optional[bytes] = None) -> str:
        if self._script is not None:
            if self._index >= len(self._script):
                return self._script[-1]
            move = self._script[self._index]
            self._index += 1
            return move
        return self._default_move(board_text)

    def choose_placement(
        self, *, board_text: str, board_png: Optional[bytes] = None
    ) -> Dict[str, str]:
        return pieces_from_board_text(board_text)

    def probe(self, *, board_text: str, board_png: Optional[bytes] = None) -> None:
        return
