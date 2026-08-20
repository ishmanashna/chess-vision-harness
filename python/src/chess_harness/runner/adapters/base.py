"""Provider adapter protocol."""

from __future__ import annotations

from typing import Dict, Optional, Protocol


class MoveAdapter(Protocol):
    provider: str

    def choose_move(self, *, board_text: str, board_png: Optional[bytes]) -> str: ...

    def choose_placement(
        self, *, board_text: str, board_png: Optional[bytes]
    ) -> Dict[str, str]: ...

    def probe(self, *, board_text: str, board_png: Optional[bytes]) -> None: ...
