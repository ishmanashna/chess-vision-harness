"""Board-identification answer schema, placement scoring, and submission.

Answer contract: a compact mapping with ONLY occupied pieces
``{"pieces": {"a1": "wR", "e8": "bK", ...}}``. Keys are absolute squares,
values are ``w``/``b`` plus a piece letter (``K Q R B N P``). The submission
is final: it is scored immediately and the attempt ends.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import chess

__all__ = [
    "validate_pieces_answer",
    "build_placement",
    "score_placement",
    "submit_answer",
]

_PIECE_RE = re.compile(r"^[wb][KQRBNP]$")

# Hard upper bounds per color/type for a legal standard-chess placement
# (promotions are explicit, so up to 9 queens / 10 rooks etc. are legal).
_MAX_PER_PIECE = {"K": 1, "Q": 9, "R": 10, "B": 10, "N": 10, "P": 8}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_square_key(key: str) -> bool:
    try:
        square = chess.parse_square(key)
    except ValueError:
        return False
    return str(key) == chess.square_name(square)


def validate_pieces_answer(pieces: Any) -> Optional[str]:
    """Validate the placement answer schema; return an error message or None.

    Rules: an object (not list/None); keys are legal absolute squares; values
    are ``w``/``b`` + piece letter; no piece code beyond the legal max for
    standard chess (an agent cannot claim three white kings).
    """
    if not isinstance(pieces, dict):
        return "answer must be an object: {\"pieces\": {\"a1\": \"wR\", ...}}"
    for square, code in pieces.items():
        if not isinstance(square, str) or not _valid_square_key(square):
            return f"invalid square name: {square!r}"
        if not isinstance(code, str) or not _PIECE_RE.match(code):
            return f"invalid piece code {code!r} (expected w/b + K Q R B N P)"
    counts: Dict[str, int] = {}
    for code in pieces.values():
        counts[code] = counts.get(code, 0) + 1
        if counts[code] > _MAX_PER_PIECE[code[1]]:
            return f"too many {code}s in one position"
    return None


def build_placement(board: chess.Board) -> Dict[str, str]:
    """Map of occupied squares -> piece code for a position (the answer)."""
    placement: Dict[str, str] = {}
    for square in range(64):
        piece = board.piece_at(square)
        if piece is None:
            continue
        color = "w" if piece.color == chess.WHITE else "b"
        placement[chess.square_name(square)] = f"{color}{piece.symbol().upper()}"
    return placement


def _status(expect: Optional[str], submit: Optional[str]) -> str:
    if expect and submit:
        if expect == submit:
            return "exact"
        if expect[0] == submit[0]:
            return "wrong_type"
        return "wrong_color"
    if expect:
        return "missing"
    return "extra"


def score_placement(
    correct: Dict[str, str], submitted: Dict[str, str]
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Score a submitted placement against the true one.

    Returns (score, per_square). Score fields per the plan: total correct
    pieces, per-piece square/color/type breakdown, missing, extra,
    misidentified, overall accuracy, and a full-position flag.
    """
    exact = wrong_type = wrong_color = missing = extra = 0
    per_square: List[Dict[str, Any]] = []
    for index in range(64):
        square = chess.square_name(index)
        expect = correct.get(square)
        submit = submitted.get(square)
        if expect is None and submit is None:
            continue
        status = _status(expect, submit)
        if status == "exact":
            exact += 1
        elif status == "wrong_type":
            wrong_type += 1
        elif status == "wrong_color":
            wrong_color += 1
        elif status == "missing":
            missing += 1
        else:
            extra += 1
        per_square.append(
            {
                "square": square,
                "expected": expect,
                "submitted": submit,
                "status": status,
            }
        )
    total = len(correct)
    accuracy = round(exact / total, 4) if total else 1.0
    full_position = len(correct) == len(submitted) and all(
        submitted.get(sq) == code for sq, code in correct.items()
    )
    return (
        {
            "total_pieces": total,
            "exact": exact,
            "wrong_type": wrong_type,
            "wrong_color": wrong_color,
            "misidentified": wrong_type + wrong_color,
            "missing": missing,
            "extra": extra,
            "accuracy": accuracy,
            "full_position": full_position,
        },
        per_square,
    )


def submit_answer(record: Dict[str, Any], pieces: Dict[str, str]) -> Dict[str, Any]:
    """Score a placement and finish the attempt (submission is final); mutates record.

    Returns an outcome dict: ``ok``, ``finished``, ``result`` (``correct`` /
    ``failed``), ``score``, and a human ``message``. A schema-invalid answer is
    a request error handled by the API layer BEFORE calling this, so this
    function only ever sees a well-formed placement.
    """
    if record.get("status") != "active":
        return {"ok": False, "finished": True, "result": None, "message": "attempt is not active"}

    score, per_square = score_placement(record["correct_pieces"], pieces)
    record["submitted_pieces"] = dict(pieces)
    record["score"] = score
    record["per_square"] = per_square
    record["status"] = "finished"
    record["result"] = "correct" if score["full_position"] else "failed"
    record["failure_reason"] = None if score["full_position"] else "placement_mismatch"
    now = _now()
    record["submitted_at"] = now
    record["finished_at"] = now
    record["updated_at"] = now
    return {
        "ok": True,
        "finished": True,
        "result": record["result"],
        "score": score,
        "message": (
            "Placement accepted — the position was identified."
            if score["full_position"]
            else "Placement accepted — mismatched against the true placement."
        ),
    }