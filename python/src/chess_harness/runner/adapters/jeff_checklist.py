"""J4: flowchart of Jeff yes/no checks, then final move Choice."""

from __future__ import annotations

from typing import Dict, List, Optional

from .typesafe import TypesafeAdapter, pick_choice


class JeffChecklistAdapter:
    """Ask Jeff a fixed checklist, then pick a move with answers in the note."""

    provider = "typesafe"

    def __init__(self, inner: TypesafeAdapter):
        self.inner = inner
        self.last_answers: Dict[str, str] = {}

    def _ask_label(self, *, board_text: str, question: str, options: List[str]) -> str:
        criteria = {opt: None for opt in options}
        state = {
            "task": "chess_checklist",
            "board_text": board_text,
            "note": question,
        }
        questions = {
            "answer": {
                "type": "choice",
                "instructions": (
                    question
                    + " Choose exactly one of the criteria keys. No other words."
                ),
                "criteria": criteria,
            }
        }
        raw = self.inner._systemone(state=state, questions=questions)
        answers = raw.get("answers") or {}
        answer = answers.get("answer") or {}
        if not isinstance(answer, dict):
            answer = {}
        return pick_choice(answer, options)

    def choose_move(self, *, board_text: str, board_png: Optional[bytes] = None) -> str:
        del board_png
        answers: Dict[str, str] = {}
        answers["in_check"] = self._ask_label(
            board_text=board_text,
            question="Are we (side to move) currently in check?",
            options=["yes", "no"],
        )
        answers["losing_hang"] = self._ask_label(
            board_text=board_text,
            question=(
                "Are any of our pieces threatened such that if the exchange "
                "is forced we lose material points?"
            ),
            options=["yes", "no"],
        )
        answers["our_equal_capture"] = self._ask_label(
            board_text=board_text,
            question=(
                "Are we threatening a capture of equal or greater value that looks safe?"
            ),
            options=["yes", "no"],
        )
        answers["useful_check"] = self._ask_label(
            board_text=board_text,
            question=(
                "Is there a check available that improves our position "
                "(not a useless check)?"
            ),
            options=["yes", "no", "none"],
        )
        answers["mate_threat"] = self._ask_label(
            board_text=board_text,
            question="Is the opponent threatening checkmate in the next move or two?",
            options=["yes", "no"],
        )
        self.last_answers = answers

        checklist = "; ".join(f"{k}={v}" for k, v in answers.items())
        self.inner.spirit = (
            "Checklist: "
            + checklist
            + ". Pick the UCI that best respects those answers."
        )
        return self.inner.choose_move(board_text=board_text, board_png=None)

    def choose_placement(self, *, board_text: str, board_png: Optional[bytes] = None):
        return self.inner.choose_placement(board_text=board_text, board_png=board_png)

    def probe(self, *, board_text: str, board_png: Optional[bytes] = None) -> None:
        self.inner.probe(board_text=board_text, board_png=board_png)
