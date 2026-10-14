"""Versioned spectator-only annotations, derived from the existing quality pass."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import chess

SCHEMA_VERSION = 1
LABEL_VERSION = "win-chance-loss-exceptional-v8"
# Mover's win-chance loss, in percentage points; not centipawn thresholds.
THRESHOLDS = {"inaccuracy": 8.0, "mistake": 10.0, "blunder": 30.0}


@lru_cache(maxsize=8)
def _binary_hash(path: str, size: int, mtime_ns: int) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def move_label(loss: float) -> str:
    if loss > THRESHOLDS["blunder"]:
        return "blunder"
    if loss >= THRESHOLDS["mistake"]:
        return "mistake"
    if loss >= THRESHOLDS["inaccuracy"]:
        return "inaccuracy"
    return "good"


def apply_preference(row, audit):
    """Do not call a deeper engine's preferred move a shallow-search error."""
    row.update({key: value for key, value in audit.items() if key.startswith("best_move_")})
    verification = audit.get("verification")
    if isinstance(verification, dict):
        row["exceptional_audit"] = deepcopy(verification)
    if (row.get("label") in {"inaccuracy", "mistake", "blunder"}
            and audit.get("best_move_uci") == row.get("uci")
            and (audit.get("best_move_depth", 0) >= 8 or audit.get("forced_choice"))):
        row["shallow_label"] = row["label"]
        row["label"] = "good"
        row["label_note"] = "The engine preferred the played move; a shallow evaluation swing is not a move error"
    return row


def position_score(board: chess.Board, cp: int, engine=None) -> dict:
    if board.is_checkmate():
        return {"cp": None, "mate": 0, "winner": "black" if board.turn else "white"}
    if board.is_game_over():
        return {"cp": 0, "mate": None}
    detail = getattr(engine, "last_evaluation", None) if engine else None
    if detail and detail.get("mate") is not None:
        mate = detail["mate"]
        return {"cp": None, "mate": mate, "winner": "white" if mate > 0 else "black"}
    return {"cp": cp, "mate": None}


def moves_hash(start_fen: str, moves: list[str]) -> str:
    return hashlib.sha256(json.dumps([start_fen, moves], separators=(",", ":")).encode()).hexdigest()


def make_analysis(start_fen, moves, rows, depth, engine=None, exceptional_enabled=False) -> dict:
    from .exceptional_moves import PROFILE
    uci = getattr(engine, "engine", None)
    identity = getattr(uci, "id", {}) or {}
    options = getattr(uci, "options", {}) or {}
    binary_hash = None
    launch = getattr(engine, "launch_command", None)
    if isinstance(launch, str):
        try:
            path = Path(launch).resolve()
            stat = path.stat()
            binary_hash = _binary_hash(str(path), stat.st_size, stat.st_mtime_ns)
        except OSError:
            pass
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete" if len(rows) == len(moves) else "incomplete",
        "analysed_at": datetime.now(timezone.utc).isoformat(),
        "moves_hash": moves_hash(start_fen, moves),
        "profile": {"quality_version": "quality-v1", "label_version": LABEL_VERSION,
                    "engine": identity.get("name", "Injected evaluator" if engine is None else "Unknown engine"),
                    "author": identity.get("author"), "depth": depth,
                    "engine_sha256": binary_hash,
                    "network": getattr(options.get("EvalFile"), "default", None),
                    "threads": getattr(options.get("Threads"), "default", None),
                    "hash_mb": getattr(options.get("Hash"), "default", None),
                    "limit_strength": False, "score_perspective": "white",
                    "budget_validated": False},
        "exceptional_profile": dict(PROFILE, enabled=exceptional_enabled),
        "thresholds": dict(THRESHOLDS), "plies": rows,
    }


def save_analysis(game_dir: Path, analysis: dict) -> None:
    game_dir.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="move-analysis-", suffix=".tmp", dir=game_dir)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(analysis, stream)
        for attempt in range(50):
            try:
                os.replace(temporary, game_dir / "move-analysis.json")
                break
            except PermissionError:
                if attempt == 49: raise
                time.sleep(.02)
    finally:
        Path(temporary).unlink(missing_ok=True)


def annotations_payload(game_dir: Path, state: dict) -> dict:
    if state.get("status") != "finished":
        return {"status": "unavailable", "reason": "Annotations are available for finished games only"}
    path = game_dir / "move-analysis.json"
    if not path.is_file():
        pending = (not state.get("quality_at") or state.get("quality_provisional")) and state.get("result") not in {None, "*"}
        return {"status": "pending" if pending else "unavailable", "reason": "Analysis pending" if pending else "No saved move analysis yet"}
    try:
        if path.stat().st_size > 2_000_000:
            raise ValueError("Analysis file too large")
        analysis = json.loads(path.read_text(encoding="utf-8"))
        expected = moves_hash(chess.Board(state.get("start_fen") or chess.STARTING_FEN).fen(), state.get("moves") or [])
        if analysis.get("schema_version") != SCHEMA_VERSION or analysis.get("moves_hash") != expected:
            return {"status": "unavailable", "reason": "Saved analysis does not match this game/version"}
        if analysis.get("status") != "complete" or len(analysis.get("plies", [])) != len(state.get("moves") or []):
            return {"status": "unavailable", "reason": "Saved analysis is incomplete"}
        # Explicit projection: never publish engine PVs or arbitrary artifact fields.
        rows = []
        board = chess.Board(state.get("start_fen") or chess.STARTING_FEN)
        for index, row in enumerate(analysis["plies"]):
            color = "white" if board.turn else "black"
            if row.get("ply") != index + 1 or row.get("uci") != state["moves"][index] or row.get("color") != color or row.get("label") not in {"good", "great", "brilliant", "inaccuracy", "mistake", "blunder"}:
                raise ValueError("Misaligned move analysis")
            projected = {key: row.get(key) for key in ("ply", "uci", "color", "loss_cp", "loss_percent", "label", "best_move_uci", "best_move_san", "best_move_depth")}
            if row.get("terminal_context"):
                projected["terminal_context"] = {key: row["terminal_context"].get(key) for key in ("kind", "reason", "game_result", "display_symbol")}
            if row["label"] in {"great", "brilliant"}:
                from .exceptional_moves import PROFILE, VERSION
                evidence = row.get("exceptional") or {}
                passes = evidence.get("passes") or []
                if evidence.get("version") != VERSION or len(passes) != 2:
                    raise ValueError("Missing exceptional-move verification")
                for item, settings in zip(passes, PROFILE["passes"]):
                    if item.get("depth", 0) < settings["minimum_depth"] or item.get("label") != row["label"]:
                        raise ValueError("Insufficient exceptional-move verification")
            for position in ("before", "after"):
                projected[position] = {key: row[position].get(key) for key in ("cp", "mate", "winner")}
            if row.get("exceptional"):
                evidence = row["exceptional"]
                projected["exceptional"] = {"version": evidence.get("version"), "policy_version": evidence.get("policy_version"), "sacrifice_cp": evidence.get("sacrifice_cp"),
                    "discovery": {key: (evidence.get("discovery") or {}).get(key) for key in ("shallow_depth", "discovered_depth", "stable_through_depth", "shallow_chance", "root_changed")},
                    "passes": [{key: item.get(key) for key in ("depth", "best_chance", "second_chance", "played_chance", "discovery_gain_pp", "label")} for item in evidence.get("passes", [])]}
            rows.append(projected)
            board.push_uci(row["uci"])
        profile = {key: analysis.get("profile", {}).get(key) for key in ("engine", "author", "engine_sha256", "network", "depth", "threads", "hash_mb", "limit_strength", "score_perspective", "quality_version", "label_version", "budget_validated")}
        exceptional = {key: analysis.get("exceptional_profile", {}).get(key) for key in ("version", "evidence_version", "enabled", "multipv", "critical_gap_pp", "minimum_chance", "alternative_winning_chance", "sacrifice_min_cp", "near_best_loss_pp", "discovery")}
        return {"status": "complete", "schema_version": SCHEMA_VERSION, "analysed_at": analysis.get("analysed_at"), "profile": profile, "exceptional_profile": exceptional, "thresholds": analysis.get("thresholds", THRESHOLDS), "plies": rows}
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        return {"status": "unavailable", "reason": "Saved analysis could not be read"}
