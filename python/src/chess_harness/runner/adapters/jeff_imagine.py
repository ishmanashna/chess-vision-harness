"""J5: Jeff proposes a move; we render the imagined board; Jeff keeps or bans."""

from __future__ import annotations

from typing import List, Optional, Set

import chess

from chess_harness.board_text import format_board_text

from .typesafe import TypesafeAdapter, board_from_board_text, legal_uci, pick_choice


class JeffImagineAdapter:
    """Jeff picks candidates; code only imagines; Jeff compares real vs imagined."""

    provider = "typesafe"

    def __init__(self, inner: TypesafeAdapter, *, max_tries: int = 5):
        self.inner = inner
        self.max_tries = max(1, int(max_tries))
        self.last_tries: List[str] = []

    def _jeff_proposes(self, board_text: str, banned: Set[str]) -> str:
        board = board_from_board_text(board_text)
        legal = [u for u in legal_uci(board) if u not in banned]
        if not legal:
            legal = legal_uci(board)
        spirit = (
            "Propose the single best legal UCI for the side to move. "
            "Do not pick a banned move."
        )
        if banned:
            spirit += " Banned (already rejected): " + ", ".join(sorted(banned)) + "."
        self.inner.spirit = spirit
        move = self.inner.choose_move(board_text=board_text, board_png=None)
        if move not in legal:
            move = legal[0]
        return move

    def _jeff_prefers_imagined(
        self, *, real_text: str, imagined_text: str, side: str
    ) -> bool:
        note = (
            f"Board A is the current position. Board B is after a candidate move by {side}. "
            f"Is Board B better for {side} than Board A? "
            "Choose exactly one criteria key."
        )
        criteria = {"better_for_us": None, "worse_for_us": None}
        state = {
            "task": "chess_compare",
            "side": side,
            "board_a_real": real_text,
            "board_b_imagined": imagined_text,
            "note": note,
        }
        questions = {
            "answer": {
                "type": "choice",
                "instructions": (
                    note
                    + "\n\nBOARD_A (real):\n"
                    + real_text
                    + "\n\nBOARD_B (imagined):\n"
                    + imagined_text
                ),
                "criteria": criteria,
            }
        }
        raw = self.inner._systemone(state=state, questions=questions)
        answers = raw.get("answers") or {}
        answer = answers.get("answer") or {}
        if not isinstance(answer, dict):
            answer = {}
        choice = pick_choice(answer, list(criteria.keys()))
        return choice == "better_for_us"

    def choose_move(self, *, board_text: str, board_png: Optional[bytes] = None) -> str:
        del board_png
        board = board_from_board_text(board_text)
        side = "white" if board.turn == chess.WHITE else "black"
        banned: Set[str] = set()
        self.last_tries = []
        last: Optional[str] = None
        for _ in range(self.max_tries):
            proposal = self._jeff_proposes(board_text, banned)
            last = proposal
            self.last_tries.append(proposal)
            try:
                move = chess.Move.from_uci(proposal)
                if move not in board.legal_moves:
                    banned.add(proposal)
                    continue
            except ValueError:
                banned.add(proposal)
                continue
            imagined = board.copy(stack=False)
            imagined.push(move)
            # Keep white-at-bottom for both boards so the compare is consistent.
            imagined_text = format_board_text(imagined, bottom_color="white")
            if self._jeff_prefers_imagined(
                real_text=board_text, imagined_text=imagined_text, side=side
            ):
                return proposal
            banned.add(proposal)
        return last or legal_uci(board)[0]

    def choose_placement(self, *, board_text: str, board_png: Optional[bytes] = None):
        return self.inner.choose_placement(board_text=board_text, board_png=board_png)

    def probe(self, *, board_text: str, board_png: Optional[bytes] = None) -> None:
        self.inner.probe(board_text=board_text, board_png=board_png)
