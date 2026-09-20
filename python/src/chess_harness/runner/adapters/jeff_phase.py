"""J3: inject phase+material spirit, then normal Typesafe Choice."""

from __future__ import annotations

from typing import Optional

from chess_harness.paths import project_root

from .jeff_phase_detect import phase_key
from .typesafe import TypesafeAdapter, board_from_board_text


def _phase_dir():
    return project_root() / "config" / "prompt_packs" / "j3_phases"


def load_phase_spirit(key: str) -> str:
    path = _phase_dir() / f"{key}.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    fb = _phase_dir() / "middle_even.txt"
    return fb.read_text(encoding="utf-8").strip() if fb.is_file() else key


class JeffPhaseAdapter:
    """Rebuild board, classify phase/material, set spirit, delegate to Typesafe."""

    provider = "typesafe"

    def __init__(self, inner: TypesafeAdapter):
        self.inner = inner
        self.last_phase_key: Optional[str] = None

    def choose_move(self, *, board_text: str, board_png: Optional[bytes] = None) -> str:
        board = board_from_board_text(board_text)
        key = phase_key(board)
        self.last_phase_key = key
        self.inner.spirit = load_phase_spirit(key)
        return self.inner.choose_move(board_text=board_text, board_png=board_png)

    def choose_placement(self, *, board_text: str, board_png: Optional[bytes] = None):
        return self.inner.choose_placement(board_text=board_text, board_png=board_png)

    def probe(self, *, board_text: str, board_png: Optional[bytes] = None) -> None:
        self.inner.probe(board_text=board_text, board_png=board_png)
