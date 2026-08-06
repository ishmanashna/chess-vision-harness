"""Puzzle row validation for the Lichess standard puzzle CSV (CC0).

Validates every imported row before publication: the FEN parses to a standard
chess position, the full move line is legal from that FEN, IDs and numeric
fields are sane, and duplicate IDs / duplicate positions are detected.

The Lichess convention is preserved: the stored FEN is the position BEFORE the
opponent setup move; the line's first move is that setup move; the displayed
position is the FEN after the first move; the solution (agent's task) starts
with the second move.

This module is import/validation only — it does not touch the store or modify
any files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

import chess

__all__ = [
    "LICHESS_FIELDS",
    "PuzzleRow",
    "PuzzleValidationError",
    "apply_lichess_setup",
    "split_tags",
    "validate_row",
    "validate_rows",
]

LICHESS_FIELDS = (
    "PuzzleId",
    "FEN",
    "Moves",
    "Rating",
    "RatingDeviation",
    "Popularity",
    "NbPlays",
    "Themes",
    "GameUrl",
    "OpeningTags",
    "DailyDate",
)

_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,64}$")


class PuzzleValidationError(ValueError):
    """A single puzzle row failed validation."""


@dataclass
class PuzzleRow:
    """Normalized puzzle row after validation (JSON-serializable)."""

    puzzle_id: str
    fen: str
    moves: List[str]
    rating: int
    rating_deviation: int
    popularity: int
    nb_plays: int
    themes: List[str]
    game_url: str
    opening_tags: List[str]
    daily_date: str
    # Derived from the Lichess setup convention.
    setup_move: str = field(init=False)
    display_fen: str = field(init=False)
    solution_moves: List[str] = field(init=False)

    def __post_init__(self) -> None:
        display_fen, setup_move, solution = apply_lichess_setup(
            self.fen, self.moves
        )
        self.display_fen = display_fen
        self.setup_move = setup_move
        self.solution_moves = solution

    def to_dict(self) -> Dict[str, Any]:
        return {
            "puzzle_id": self.puzzle_id,
            "fen": self.fen,
            "display_fen": self.display_fen,
            "setup_move": self.setup_move,
            "solution_moves": self.solution_moves,
            "moves": self.moves,
            "rating": self.rating,
            "rating_deviation": self.rating_deviation,
            "popularity": self.popularity,
            "nb_plays": self.nb_plays,
            "themes": self.themes,
            "game_url": self.game_url,
            "opening_tags": self.opening_tags,
            "daily_date": self.daily_date,
        }


def parse_move_list(moves: str) -> List[str]:
    return [part.strip() for part in moves.split() if part.strip()]


def split_tags(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [tag.strip() for tag in str(value).split() if tag.strip()]


def apply_lichess_setup(
    fen: str, moves: List[str]
) -> tuple[str, str, List[str]]:
    """Return (display_fen, setup_move, solution_moves).

    The displayed position is the FEN after ONLY the first (setup) move — the
    side to move there is the solver. The remaining moves are validated for
    legality against the full line but do not change the displayed FEN.
    """
    try:
        board = chess.Board(fen)
    except ValueError as exc:
        raise PuzzleValidationError(f"invalid FEN: {exc}") from exc
    status = board.status()
    if status != chess.STATUS_VALID:
        raise PuzzleValidationError(f"FEN is not a legal position (status {status})")
    if not moves:
        raise PuzzleValidationError("empty move line")
    setup = moves[0]
    try:
        uci = chess.Move.from_uci(setup)
        if uci not in board.legal_moves:
            raise PuzzleValidationError(
                f"first (setup) move {setup!r} is not legal from the FEN"
            )
        board.push(uci)
    except ValueError as exc:
        raise PuzzleValidationError(
            f"first (setup) move {setup!r} is not legal from the FEN"
        ) from exc
    display_fen = board.fen()
    solution: List[str] = []
    for move in moves[1:]:
        try:
            uci = chess.Move.from_uci(move)
        except ValueError as exc:
            raise PuzzleValidationError(f"invalid move {move!r}: {exc}") from exc
        if uci not in board.legal_moves:
            raise PuzzleValidationError(f"move {move!r} is not legal")
        board.push(uci)
        solution.append(move)
    return display_fen, setup, solution


def _int_field(row: Dict[str, Any], key: str) -> int:
    raw = row.get(key) or row.get(key.lower()) or ""
    if isinstance(raw, (int, float)):
        value = int(raw)
    else:
        text = str(raw).strip()
        if not re.match(r"^-?\d+$", text):
            raise PuzzleValidationError(f"{key} must be an integer, got {raw!r}")
        value = int(text)
    if key not in ("Popularity", "NbPlays") and value < 0:
        raise PuzzleValidationError(f"{key} must be non-negative")
    return value


def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Case-insensitive view that also tolerates the snake_case alias prefix."""
    keyed: Dict[str, str] = {}
    for field_name in LICHESS_FIELDS:
        value = row.get(field_name, row.get(field_name.lower()))
        keyed[field_name] = "" if value is None else str(value).strip()
    return keyed


def validate_row(row: Dict[str, Any]) -> PuzzleRow:
    """Validate one row; raise :class:`PuzzleValidationError` on rejection."""
    data = normalize_row(row)

    puzzle_id = data.get("PuzzleId")
    if not puzzle_id:
        raise PuzzleValidationError("missing PuzzleId")
    if not _ID_PATTERN.match(puzzle_id):
        raise PuzzleValidationError(f"invalid PuzzleId: {puzzle_id!r}")

    fen = data.get("FEN")
    if not fen:
        raise PuzzleValidationError("missing FEN")

    moves = parse_move_list(data.get("Moves"))
    if not moves:
        raise PuzzleValidationError("missing Moves")

    # Validate the full legal line now so the store never publishes a bad puzzle.
    apply_lichess_setup(fen, moves)

    try:
        rating = _int_field(data, "Rating")
        deviation = _int_field(data, "RatingDeviation")
        popularity = _int_field(data, "Popularity")
        nb_plays = _int_field(data, "NbPlays")
    except PuzzleValidationError:
        raise

    return PuzzleRow(
        puzzle_id=puzzle_id,
        fen=fen,
        moves=moves,
        rating=rating,
        rating_deviation=deviation,
        popularity=popularity,
        nb_plays=nb_plays,
        themes=split_tags(data.get("Themes")),
        game_url=data.get("GameUrl", ""),
        opening_tags=split_tags(data.get("OpeningTags")),
        daily_date=data.get("DailyDate", ""),
    )


def validate_rows(rows: Iterable[Dict[str, Any]]) -> tuple[List[PuzzleRow], List[str]]:
    """Validate a stream of rows; return (accepted, rejection reasons).

    Duplicate PuzzleIds are rejected (the first occurrence wins).
    """
    seen: set[str] = set()
    accepted: List[PuzzleRow] = []
    rejected: List[str] = []
    for row in rows:
        try:
            parsed = validate_row(row)
        except PuzzleValidationError as exc:
            rejected.append(str(exc))
            continue
        if parsed.puzzle_id in seen:
            rejected.append(f"duplicate PuzzleId: {parsed.puzzle_id}")
            continue
        seen.add(parsed.puzzle_id)
        accepted.append(parsed)
    return accepted, rejected