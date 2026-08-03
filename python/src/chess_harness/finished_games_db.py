"""Permanent finished-games SQLite store (dual-written on scored finish).

Live play stays on the filesystem; this DB is the forever record. Official
delete/prune/remove of live game dirs must never DELETE rows here.

Default path: ``data/finished_games.sqlite`` (repo-relative, git-tracked).
Override with ``CHESS_HARNESS_FINISHED_DB`` for experiments only.

Operators should commit the DB file periodically so GitHub retains history.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .game_types import DEFAULT_GAME_TYPE
from .paths import resolve_finished_games_db

_log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS finished_games (
    game_id TEXT PRIMARY KEY,
    game_type TEXT,
    finished_at TEXT,
    end_reason TEXT,
    result TEXT NOT NULL,
    model_id TEXT,
    model_display_name TEXT,
    agent_color TEXT,
    white_model_id TEXT,
    black_model_id TEXT,
    white_display_name TEXT,
    black_display_name TEXT,
    human_nickname TEXT,
    opponent_id TEXT,
    opponent_elo REAL,
    moves_uci_json TEXT,
    pgn_text TEXT,
    final_fen TEXT,
    plies INTEGER,
    pgn_headers_json TEXT,
    agent_accuracy REAL,
    agent_play_rating REAL,
    white_accuracy REAL,
    black_accuracy REAL,
    white_play_rating REAL,
    black_play_rating REAL,
    quality_meta_json TEXT,
    elo_before INTEGER,
    elo_after INTEGER,
    elo_delta INTEGER,
    white_elo_before INTEGER,
    white_elo_after INTEGER,
    black_elo_before INTEGER,
    black_elo_after INTEGER,
    state_json TEXT NOT NULL,
    results_json TEXT,
    recorded_at TEXT NOT NULL
);
"""

_UPSERT_COLS: Tuple[str, ...] = (
    "game_id",
    "game_type",
    "finished_at",
    "end_reason",
    "result",
    "model_id",
    "model_display_name",
    "agent_color",
    "white_model_id",
    "black_model_id",
    "white_display_name",
    "black_display_name",
    "human_nickname",
    "opponent_id",
    "opponent_elo",
    "moves_uci_json",
    "pgn_text",
    "final_fen",
    "plies",
    "pgn_headers_json",
    "agent_accuracy",
    "agent_play_rating",
    "white_accuracy",
    "black_accuracy",
    "white_play_rating",
    "black_play_rating",
    "quality_meta_json",
    "elo_before",
    "elo_after",
    "elo_delta",
    "white_elo_before",
    "white_elo_after",
    "black_elo_before",
    "black_elo_after",
    "state_json",
    "results_json",
    "recorded_at",
)


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else resolve_finished_games_db()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def get_finished_game(
    game_id: str, *, db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM finished_games WHERE game_id = ?", (game_id,)
        ).fetchone()
    return dict(row) if row else None


def list_finished_games(*, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Return finished game rows (id, result, timestamps) newest first."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT game_id, result, finished_at, game_type, model_id, "
            "recorded_at FROM finished_games "
            "ORDER BY finished_at DESC, game_id"
        ).fetchall()
    return [dict(r) for r in rows]


def restore_finished_game(
    game_id: str,
    *,
    db_path: Optional[Path] = None,
    game_manager: Any = None,
    results_manager: Any = None,
) -> Dict[str, Any]:
    """Recreate live ``games/<id>/`` from DB state + PGN; merge results if missing.

    Does not invent board PNGs — next view/serve re-renders from FEN.
    """
    from .game_manager import GameManager
    from .results import ResultsManager

    row = get_finished_game(game_id, db_path=db_path)
    if row is None:
        raise KeyError(f"No finished game in DB: {game_id}")

    gm = game_manager if game_manager is not None else GameManager()
    rm = results_manager if results_manager is not None else ResultsManager(
        base_dir=str(gm.base_dir)
    )

    state = json.loads(row["state_json"])
    if not gm.save_state(game_id, state):
        raise OSError(f"Failed to write state for {game_id}")

    pgn_text = row.get("pgn_text")
    if pgn_text:
        gm.get_pgn_path(game_id).write_text(pgn_text, encoding="utf-8")

    results_merged = 0
    existing = [r for r in rm.load_results() if r.get("game_id") == game_id]
    if not existing and row.get("results_json"):
        for result_row in json.loads(row["results_json"]):
            if rm.append_result(result_row):
                results_merged += 1

    return {
        "game_id": game_id,
        "results_merged": results_merged,
        "had_pgn": bool(pgn_text),
        "db_path": str(Path(db_path) if db_path else resolve_finished_games_db()),
    }


def record_scored_finish(
    game_id: str,
    state: Dict[str, Any],
    *,
    db_path: Optional[Path] = None,
    game_manager: Any = None,
    results_manager: Any = None,
) -> bool:
    """Upsert a scored finished game. Skips ``result == '*'``. Fail-soft."""
    result = state.get("result")
    if result is None or result == "*":
        return False
    if state.get("status") != "finished":
        return False
    try:
        upsert_finished_game(
            game_id,
            state,
            db_path=db_path,
            game_manager=game_manager,
            results_manager=results_manager,
        )
        return True
    except Exception:
        _log.exception("finished-games dual-write failed for %s", game_id)
        return False


def upsert_finished_game(
    game_id: str,
    state: Dict[str, Any],
    *,
    db_path: Optional[Path] = None,
    pgn_text: Optional[str] = None,
    results_rows: Optional[List[Dict[str, Any]]] = None,
    game_manager: Any = None,
    results_manager: Any = None,
) -> None:
    """Idempotent upsert by ``game_id``. Caller must skip ``*`` / unscored."""
    if pgn_text is None and game_manager is not None:
        pgn_path = game_manager.get_pgn_path(game_id)
        if pgn_path.exists():
            try:
                pgn_text = pgn_path.read_text(encoding="utf-8")
            except OSError:
                pgn_text = None

    if results_rows is None and results_manager is not None:
        results_rows = [
            row
            for row in results_manager.load_results()
            if row.get("game_id") == game_id
        ]

    row = _row_from_state(game_id, state, pgn_text=pgn_text, results_rows=results_rows)
    placeholders = ", ".join("?" for _ in _UPSERT_COLS)
    col_list = ", ".join(_UPSERT_COLS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in _UPSERT_COLS if c != "game_id")
    sql = (
        f"INSERT INTO finished_games ({col_list}) VALUES ({placeholders}) "
        f"ON CONFLICT(game_id) DO UPDATE SET {updates}"
    )
    values = [row[c] for c in _UPSERT_COLS]
    with connect(db_path) as conn:
        conn.execute(sql, values)
        conn.commit()


def reconcile_finished_games(
    *, db_path: Optional[Path] = None, game_manager: Any = None
) -> Dict[str, List[str]]:
    """Report scored live games missing from SQLite and database-only rows."""
    from .game_manager import GameManager

    gm = game_manager if game_manager is not None else GameManager()
    with connect(db_path) as conn:
        db_ids = {row[0] for row in conn.execute("SELECT game_id FROM finished_games")}
    live_scored = {
        game["game_id"]
        for game in gm.list_games(status_filter="finished")
        if game["state"].get("result") not in (None, "*")
    }
    return {
        "live_missing_from_db": sorted(live_scored - db_ids),
        "db_without_live_game": sorted(db_ids - live_scored),
    }


def import_live_finished_games(
    *,
    db_path: Optional[Path] = None,
    game_manager: Any = None,
    results_manager: Any = None,
) -> Dict[str, Any]:
    """Scan live ``games/*/state.json`` and upsert finished scored games.

    Skips in-progress and ``result == '*'``. Merges matching ``results.jsonl``
    rows per game_id. Idempotent: re-import upserts the same ``game_id`` set.
    """
    from .game_manager import GameManager
    from .results import ResultsManager

    gm = game_manager if game_manager is not None else GameManager()
    rm = results_manager if results_manager is not None else ResultsManager(
        base_dir=str(gm.base_dir)
    )

    results_by_id: Dict[str, List[Dict[str, Any]]] = {}
    for row in rm.load_results():
        gid = row.get("game_id")
        if not gid:
            continue
        results_by_id.setdefault(gid, []).append(row)

    imported: List[str] = []
    skipped = 0
    for game in gm.list_games(status_filter="finished"):
        game_id = game["game_id"]
        state = game["state"]
        result = state.get("result")
        if result is None or result == "*":
            skipped += 1
            continue
        upsert_finished_game(
            game_id,
            state,
            db_path=db_path,
            game_manager=gm,
            results_rows=results_by_id.get(game_id, []),
        )
        imported.append(game_id)

    return {
        "imported": len(imported),
        "skipped": skipped,
        "game_ids": imported,
        "db_path": str(Path(db_path) if db_path else resolve_finished_games_db()),
    }


def _json_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value)


def _row_from_state(
    game_id: str,
    state: Dict[str, Any],
    *,
    pgn_text: Optional[str],
    results_rows: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    moves = state.get("moves") or []
    quality_meta = {
        k: state[k]
        for k in (
            "quality_at",
            "quality_depth",
            "quality_thin",
            "quality_provisional",
            "quality_move_count",
        )
        if k in state
    }
    finished_at = None
    if results_rows:
        finished_at = results_rows[0].get("ts")
    if not finished_at:
        finished_at = datetime.now(timezone.utc).isoformat()

    return {
        "game_id": game_id,
        "game_type": state.get("game_type") or DEFAULT_GAME_TYPE,
        "finished_at": finished_at,
        "end_reason": state.get("end_reason"),
        "result": state.get("result"),
        "model_id": state.get("model_name"),
        "model_display_name": state.get("model_display_name"),
        "agent_color": state.get("agent_color"),
        "white_model_id": state.get("white_model_id"),
        "black_model_id": state.get("black_model_id"),
        "white_display_name": state.get("white_display_name"),
        "black_display_name": state.get("black_display_name"),
        "human_nickname": state.get("human_nickname"),
        "opponent_id": state.get("opponent_id"),
        "opponent_elo": state.get("opponent_elo"),
        "moves_uci_json": json.dumps(moves),
        "pgn_text": pgn_text,
        "final_fen": state.get("board_fen"),
        "plies": len(moves),
        "pgn_headers_json": _json_or_none(state.get("pgn_headers")),
        "agent_accuracy": state.get("agent_accuracy"),
        "agent_play_rating": state.get("agent_play_rating"),
        "white_accuracy": state.get("white_accuracy"),
        "black_accuracy": state.get("black_accuracy"),
        "white_play_rating": state.get("white_play_rating"),
        "black_play_rating": state.get("black_play_rating"),
        "quality_meta_json": _json_or_none(quality_meta) if quality_meta else None,
        "elo_before": state.get("elo_before"),
        "elo_after": state.get("elo_after"),
        "elo_delta": state.get("elo_delta"),
        "white_elo_before": state.get("white_elo_before"),
        "white_elo_after": state.get("white_elo_after"),
        "black_elo_before": state.get("black_elo_before"),
        "black_elo_after": state.get("black_elo_after"),
        "state_json": json.dumps(state),
        "results_json": _json_or_none(results_rows),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
