"""Localhost puzzle-set panel: imported corpus summary and per-puzzle stats."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import chess

from .board_text import bottom_color_for_board
from .identify_attempt import IdentifyAttemptStore
from .identify_scoring import build_placement
from .puzzle_attempt import PuzzleAttemptStore
from .puzzle_store import PuzzleStore
from .render_pillow import ChessBoardRenderer

__all__ = [
    "build_puzzle_preview_payload",
    "build_puzzle_set_payload",
    "render_puzzle_preview_board_png",
]

DATA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _finished_puzzle(record: Dict[str, Any]) -> bool:
    return record.get("status") == "finished" and record.get("result") in (
        "correct",
        "failed",
    )


def _finished_identify(record: Dict[str, Any]) -> bool:
    if record.get("status") != "finished":
        return False
    score = record.get("score")
    return isinstance(score, dict) and score.get("accuracy") is not None


def _row_rate(numerator: int, denominator: int) -> Optional[float]:
    return round(numerator / denominator, 4) if denominator else None


def _compact_themes(themes: Any) -> str:
    if not themes:
        return ""
    if isinstance(themes, str):
        return themes.replace(" ", ", ")
    return ", ".join(str(theme) for theme in themes)


def _side_to_move(record: Dict[str, Any]) -> Optional[str]:
    fen = str(record.get("display_fen") or "")
    if not fen:
        return None
    try:
        return "white" if chess.Board(fen).turn == chess.WHITE else "black"
    except ValueError:
        return None


def build_puzzle_set_payload(
    *,
    puzzles: Optional[PuzzleStore] = None,
    puzzle_attempts: Optional[PuzzleAttemptStore] = None,
    identify_attempts: Optional[IdentifyAttemptStore] = None,
) -> Dict[str, Any]:
    """Summary plus one row per imported puzzle (no solutions or FEN)."""
    puzzle_store = puzzles or PuzzleStore()
    attempt_store = puzzle_attempts or PuzzleAttemptStore()
    identify_store = identify_attempts or IdentifyAttemptStore()

    corpus = puzzle_store.load()
    summary = dict(puzzle_store.stats())

    puzzle_stats: Dict[str, Dict[str, Any]] = {}
    puzzle_latest: Dict[str, str] = {}
    puzzle_latest_at: Dict[str, str] = {}
    for record in attempt_store.list_records():
        if not _finished_puzzle(record):
            continue
        puzzle_id = str(record.get("puzzle_id") or "")
        if not puzzle_id:
            continue
        entry = puzzle_stats.setdefault(puzzle_id, {"attempts": 0, "solves": 0})
        entry["attempts"] += 1
        if record.get("result") == "correct":
            entry["solves"] += 1
        started = str(record.get("started_at") or "")
        if started >= puzzle_latest_at.get(puzzle_id, ""):
            puzzle_latest_at[puzzle_id] = started
            puzzle_latest[puzzle_id] = str(record.get("attempt_id") or "")

    identify_stats: Dict[str, Dict[str, Any]] = {}
    identify_latest: Dict[str, str] = {}
    identify_latest_at: Dict[str, str] = {}
    for record in identify_store.list_records():
        if not _finished_identify(record):
            continue
        puzzle_id = str(record.get("puzzle_id") or "")
        if not puzzle_id:
            continue
        score = record.get("score") or {}
        entry = identify_stats.setdefault(
            puzzle_id, {"attempts": 0, "acc_sum": 0.0, "full": 0}
        )
        entry["attempts"] += 1
        entry["acc_sum"] += float(score["accuracy"])
        if score.get("full_position"):
            entry["full"] += 1
        started = str(record.get("started_at") or "")
        if started >= identify_latest_at.get(puzzle_id, ""):
            identify_latest_at[puzzle_id] = started
            identify_latest[puzzle_id] = str(record.get("attempt_id") or "")

    never_attempted = 0
    rows: List[Dict[str, Any]] = []
    for puzzle_id, record in sorted(corpus.items(), key=lambda item: str(item[0])):
        pz = puzzle_stats.get(puzzle_id, {"attempts": 0, "solves": 0})
        iz = identify_stats.get(
            puzzle_id, {"attempts": 0, "acc_sum": 0.0, "full": 0}
        )
        if pz["attempts"] == 0 and iz["attempts"] == 0:
            never_attempted += 1
        iz_attempts = iz["attempts"]
        rows.append(
            {
                "id": puzzle_id,
                "difficulty": int(record.get("rating") or 0) or None,
                "side_to_move": _side_to_move(record),
                "themes": _compact_themes(record.get("themes")),
                "puzzle_attempts": pz["attempts"],
                "puzzle_solves": pz["solves"],
                "puzzle_solve_rate": _row_rate(pz["solves"], pz["attempts"]),
                "identify_attempts": iz_attempts,
                "identify_full": iz["full"],
                "identify_full_rate": _row_rate(iz["full"], iz_attempts),
                "identify_mean_accuracy": (
                    round(iz["acc_sum"] / iz_attempts, 4) if iz_attempts else None
                ),
                "watch_puzzle": (
                    f"/p/{puzzle_latest[puzzle_id]}"
                    if puzzle_latest.get(puzzle_id)
                    else None
                ),
                "watch_identify": (
                    f"/i/{identify_latest[puzzle_id]}"
                    if identify_latest.get(puzzle_id)
                    else None
                ),
            }
        )

    summary["never_attempted"] = never_attempted
    manifest = puzzle_store.manifest()
    return {
        "version": DATA_VERSION,
        "generated_at": _now(),
        "dataset_version": manifest.get("dataset_version", "unknown"),
        "summary": summary,
        "puzzles": rows,
    }


def _corpus_record(
    puzzle_id: str, *, puzzles: Optional[PuzzleStore] = None
) -> Optional[Dict[str, Any]]:
    store = puzzles or PuzzleStore()
    record = store.get(puzzle_id)
    if not record:
        return None
    display_fen = str(record.get("display_fen") or "")
    if not display_fen:
        return None
    try:
        chess.Board(display_fen)
    except ValueError:
        return None
    return record


def build_puzzle_preview_payload(
    puzzle_id: str,
    *,
    puzzles: Optional[PuzzleStore] = None,
) -> Optional[Dict[str, Any]]:
    """Operator preview: metadata, solution line, and computed identify placement."""
    record = _corpus_record(puzzle_id, puzzles=puzzles)
    if record is None:
        return None
    display_fen = str(record["display_fen"])
    board = chess.Board(display_fen)
    return {
        "id": puzzle_id,
        "difficulty": int(record.get("rating") or 0) or None,
        "side_to_move": _side_to_move(record),
        "themes": _compact_themes(record.get("themes")),
        "solution_moves": list(record.get("solution_moves") or []),
        "placement": build_placement(board),
        "board_url": f"/api/puzzle-set/{puzzle_id}/preview/board.png",
    }


def render_puzzle_preview_board_png(
    puzzle_id: str,
    *,
    puzzles: Optional[PuzzleStore] = None,
) -> Optional[bytes]:
    record = _corpus_record(puzzle_id, puzzles=puzzles)
    if record is None:
        return None
    board = chess.Board(str(record["display_fen"]))
    return ChessBoardRenderer().render_board_bytes(
        board, bottom_color=bottom_color_for_board(board)
    )
