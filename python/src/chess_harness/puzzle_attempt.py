"""Puzzle attempt lifecycle store and authoritative continuation engine.

Puzzle attempts are not games: they live in their own atomic JSON store
(``$CHESS_HARNESS_DIR/puzzle_attempts.json``), never in ``results.jsonl``,
and never count against game or move caps.

An attempt starts from the puzzle's displayed position (after the setup
move). The imported solution line is the authoritative continuation: the
agent's correct move is applied, then the next solution move (the opponent
reply) is applied immediately, so the board always shows the position before
the agent's next expected move. An illegal or wrong move ends the attempt
immediately as failed — no retry within one attempt.

The record itself contains hidden puzzle metadata (current FEN, solution
line, imported difficulty). This module never renders it; the API layer is
responsible for keeping those fields private until the attempt completes.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import chess
import filelock

from .paths import resolve_puzzle_attempts_file

__all__ = [
    "PuzzleAttemptStore",
    "apply_submission",
    "parse_agent_move",
    "session_exclude_sec",
]

DATA_VERSION = 1


def session_exclude_sec() -> int:
    """Operator-tunable 'same session' window for re-selection avoidance."""
    raw = os.environ.get("CHESS_HARNESS_PUZZLE_SESSION_EXCLUDE_SEC", "")
    try:
        return max(60, int(raw))
    except ValueError:
        return 3600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def _parse_time(value: Optional[str]) -> float:
    if not value:
        return 0.0
    try:
        parsed = datetime.fromisoformat(str(value))
        return parsed.timestamp()
    except ValueError:
        return 0.0


def parse_agent_move(board: chess.Board, raw: str) -> Optional[chess.Move]:
    """Parse UCI first, then SAN; return None if illegal or unparseable."""
    move_str = (raw or "").strip()
    if not move_str:
        return None
    try:
        move = chess.Move.from_uci(move_str)
        if move in board.legal_moves:
            return move
    except ValueError:
        pass
    try:
        return board.parse_san(move_str)
    except (chess.InvalidMoveError, chess.AmbiguousMoveError, chess.IllegalMoveError):
        return None


def apply_submission(record: Dict[str, Any], raw_move: str) -> Dict[str, Any]:
    """Advance (or fail) an attempt with one submitted move; mutates record.

    Returns an outcome dict: ``ok`` (submission accepted), ``finished``
    (attempt reached a terminal state now), ``result`` (``correct`` /
    ``failed``), ``reason`` (``wrong_move`` / ``illegal_move``), and a
    human ``message``. An illegal or wrong move ends the attempt as failed;
    there is no retry within one attempt.
    """
    if record.get("status") != "active":
        return {"ok": False, "finished": True, "result": None, "message": "attempt is not active"}

    board = chess.Board(record["board_fen"])
    move = parse_agent_move(board, raw_move)
    if move is None:
        return _fail(record, raw_move, "illegal_move")

    solution = record["solution_moves"]
    index = record["solution_index"]
    if index >= len(solution):
        return _fail(record, raw_move, "wrong_move")

    if move != chess.Move.from_uci(solution[index]):
        record["submitted_moves"].append(move.uci())
        return _fail(record, raw_move, "wrong_move")

    record["submitted_moves"].append(move.uci())
    board.push(move)

    if index + 1 < len(solution):
        reply = chess.Move.from_uci(solution[index + 1])
        record["opponent_moves"].append(reply.uci())
        board.push(reply)
        record["solution_index"] = index + 2
    else:
        record["solution_index"] = index + 1

    record["updated_at"] = _now()
    record["board_fen"] = board.fen()

    if record["solution_index"] >= len(solution):
        return _finish(record, "correct")
    return {
        "ok": True,
        "finished": False,
        "result": None,
        "message": "Correct move — the puzzle continues.",
    }


def _fail(record: Dict[str, Any], raw: str, reason: str) -> Dict[str, Any]:
    record["first_wrong_move"] = (raw or "").strip()
    record["failure_reason"] = reason
    return _finish(record, "failed")


def _finish(record: Dict[str, Any], result: str) -> Dict[str, Any]:
    record["status"] = "finished"
    record["result"] = result
    record["finished_at"] = _now()
    record["updated_at"] = _now()
    if result == "failed":
        message = "Wrong move — the attempt is failed (no retry)."
    else:
        message = "Solved — the puzzle is complete."
    return {"ok": True, "finished": True, "result": result, "message": message}


class PuzzleAttemptStore:
    """Atomic JSON store for puzzle attempts."""

    def __init__(self, path: Optional[Path] = None):
        self.path = path or resolve_puzzle_attempts_file()
        self._lock = filelock.FileLock(str(self.path) + ".lock", timeout=30)

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {"version": DATA_VERSION, "attempts": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": DATA_VERSION, "attempts": {}}
        if not isinstance(data, dict) or not isinstance(data.get("attempts"), dict):
            return {"version": DATA_VERSION, "attempts": {}}
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{self.path.name}.", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def create(
        self,
        *,
        puzzle_id: str,
        key_fingerprint: str,
        model_id: str,
        rating_min: Optional[int],
        rating_max: Optional[int],
        theme: Optional[str],
        start_fen: str,
        board_fen: str,
        solution_moves: List[str],
        puzzle_rating: int,
        content_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = _now()
        attempt: Dict[str, Any] = {
            "attempt_id": f"pz-{secrets.token_urlsafe(16)}",
            "puzzle_id": puzzle_id,
            "key_fingerprint": key_fingerprint,
            "model_id": model_id,
            "status": "active",
            "result": None,
            "failure_reason": None,
            "first_wrong_move": None,
            "rating_min": rating_min,
            "rating_max": rating_max,
            "theme": theme,
            "start_fen": start_fen,
            "board_fen": board_fen,
            "solution_moves": list(solution_moves),
            "solution_index": 0,
            "submitted_moves": [],
            "opponent_moves": [],
            "puzzle_rating": puzzle_rating,
            "content_version": content_version,
            "rating_before": None,
            "rating_after": None,
            "rating_change": None,
            "rating_deviation_before": None,
            "rating_deviation_after": None,
            "puzzle_rating_before": None,
            "puzzle_rating_after": None,
            "puzzle_rating_change": None,
            "elapsed_seconds": None,
            "started_at": now,
            "updated_at": now,
            "finished_at": None,
        }
        with self._lock:
            data = self._load()
            data["attempts"][attempt["attempt_id"]] = attempt
            self._save(data)
        return dict(attempt)

    def get(self, attempt_id: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        record = data["attempts"].get(attempt_id)
        return dict(record) if record else None

    def update(
        self, attempt_id: str, fn: Callable[[Dict[str, Any]], None]
    ) -> Optional[Dict[str, Any]]:
        """Mutate and persist under the store lock; returns the new record."""
        with self._lock:
            data = self._load()
            record = data["attempts"].get(attempt_id)
            if record is None:
                return None
            fn(record)
            self._save(data)
        return dict(record)

    def active_count(self, key_fingerprint: str) -> int:
        data = self._load()
        return sum(
            1
            for record in data["attempts"].values()
            if record.get("key_fingerprint") == key_fingerprint
            and record.get("status") == "active"
        )

    def list_records(self) -> List[Dict[str, Any]]:
        """All attempt records (public browse calls sort + filter)."""
        return list(self._load()["attempts"].values())

    def recent_puzzle_ids(
        self, key_fingerprint: str, window_sec: float
    ) -> Set[str]:
        """Puzzle ids to avoid re-selecting for this key: any attempt that is
        still active or that started within the same-session window."""
        cutoff = _now_epoch() - max(0.0, float(window_sec))
        excluded: Set[str] = set()
        for record in self._load()["attempts"].values():
            if record.get("key_fingerprint") != key_fingerprint:
                continue
            if record.get("status") == "active" or _parse_time(
                record.get("started_at")
            ) >= cutoff:
                excluded.add(record.get("puzzle_id"))
        return excluded
