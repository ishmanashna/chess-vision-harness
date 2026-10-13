"""Resumable annotation-only archive backfill. Never updates scores or game state.

Run: python -m chess_harness.annotation_backfill --workers 4
Progress: <runtime>/logs/annotation-backfill.json
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

import chess
import chess.pgn
from filelock import FileLock

from .game_manager import GameManager
from .game_quality import analyse_game, default_quality_depth
from .move_annotations import LABEL_VERSION, THRESHOLDS, annotations_payload, apply_preference, make_analysis, move_label, moves_hash, save_analysis
from .ops_online_state import operation_lock
from .paths import resolve_base_dir, resolve_finished_games_db


def inventory(root, database):
    """Prefer live filesystem state; retain archive-only games as sidecar artifacts."""
    gm = GameManager(str(root))
    games = {}
    if database.is_file():
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            for game_id, raw in connection.execute("SELECT game_id, state_json FROM finished_games"):
                if gm.validate_game_id(game_id):
                    games[game_id] = (json.loads(raw), root / "archived-move-analysis" / game_id, "archive")
    for path in sorted((root / "games").glob("*/state.json")):
        if gm.validate_game_id(path.parent.name):
            games[path.parent.name] = (json.loads(path.read_text(encoding="utf-8")), path.parent, "local")
    return {key: value for key, value in games.items()
            if value[0].get("status") == "finished" and
            (value[0].get("game_type") in {"agent_vs_engine", "agent_vs_agent", "human_vs_agent"}
             or value[0].get("model_name") or value[0].get("white_model_id") or value[0].get("black_model_id"))}


def pgn_from_state(state):
    board = chess.Board(state.get("start_fen") or chess.STARTING_FEN)
    game = chess.pgn.Game()
    game.setup(board)
    node = game
    for uci in state.get("moves") or []:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ValueError("Illegal saved move: " + uci)
        node = node.add_variation(move)
        board.push(move)
    game.headers["Result"] = state.get("result") or "*"
    return str(game)


def refresh_labels(state, artifact):
    """Reuse saved evals and reverify every move, including prior positives."""
    from .engine import EvalEngineAdapter
    from .exceptional_moves import PROFILE, classify_exceptional
    engine = None
    board = chess.Board(state.get("start_fen") or chess.STARTING_FEN)
    try:
        for row in artifact["plies"]:
            move = chess.Move.from_uci(row["uci"])
            row["label"] = move_label(row["loss_percent"])
            row.pop("exceptional", None)
            if engine is None: engine = EvalEngineAdapter()
            audit = {}
            exceptional = classify_exceptional(board, move, engine, audit=audit)
            if exceptional:
                row.update(label=exceptional["label"], exceptional=exceptional["evidence"])
            apply_preference(row, audit)
            board.push(move)
    finally:
        if engine: engine.quit()
    artifact["profile"]["label_version"] = LABEL_VERSION
    artifact["thresholds"] = dict(THRESHOLDS)
    artifact["exceptional_profile"] = dict(PROFILE, enabled=True)
    artifact["labels_refreshed_at"] = datetime.now(timezone.utc).isoformat()
    artifact["label_refresh_scope"] = "All moves reverified for critical, tactical-refinement, discovery and sacrifice criteria; old positives not grandfathered"
    from .annotation_context import apply_terminal_context
    apply_terminal_context(state, artifact)
    return artifact


def backfill_game(state, directory, run_id, depth, analyser=analyse_game, refresh=False):
    existing = annotations_payload(directory, state)
    profile = existing.get("profile") or {}
    if (existing.get("status") == "complete" and profile.get("label_version") == LABEL_VERSION
            and profile.get("depth") == depth and existing.get("exceptional_profile", {}).get("enabled")):
        return "existing"
    expected = moves_hash(chess.Board(state.get("start_fen") or chess.STARTING_FEN).fen(), state.get("moves") or [])
    if refresh and existing.get("status") == "complete" and profile.get("depth") == depth:
        artifact = refresh_labels(state, json.loads((directory / "move-analysis.json").read_text(encoding="utf-8")))
    elif state.get("moves"):
        artifact = analyser(pgn_from_state(state), depth=depth, include_exceptional=True).move_analysis
    else:
        artifact = make_analysis(chess.Board(state.get("start_fen") or chess.STARTING_FEN).fen(), [], [], depth, exceptional_enabled=True)
    if not artifact or artifact.get("moves_hash") != expected or artifact.get("status") != "complete":
        raise ValueError("Analysis did not match saved moves")
    # Validate with the same public projection before replacing anything.
    with tempfile.TemporaryDirectory(prefix="annotation-validation-") as temporary:
        save_analysis(Path(temporary), artifact)
        if annotations_payload(Path(temporary), state).get("status") != "complete":
            raise ValueError("Annotation validation failed")
    state_path = directory / "state.json"
    if state_path.exists():
        current = json.loads(state_path.read_text(encoding="utf-8"))
        current_hash = moves_hash(chess.Board(current.get("start_fen") or chess.STARTING_FEN).fen(), current.get("moves") or [])
        if current.get("status") != "finished" or current_hash != expected:
            raise ValueError("Game changed during backfill")
    old = directory / "move-analysis.json"
    if old.exists():
        backup = directory / "analysis-history" / run_id
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, backup / old.name)
    save_analysis(directory, dict(artifact, backfill_run=run_id))
    return "written"


def write_progress(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix="annotation-progress-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
        for attempt in range(50):
            try:
                os.replace(name, path)
                break
            except PermissionError:
                if attempt == 49: raise
                time.sleep(.02)
    finally:
        Path(name).unlink(missing_ok=True)


def run(root, database, workers=4, depth=None, refresh=False, priority=None):
    depth = depth or default_quality_depth()
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    lock = FileLock(str(root / "logs" / "annotation-backfill.lock"), timeout=0)
    # Do not race an operator restart at admission; release Go Online lock after admission.
    with operation_lock(root):
        lock.acquire()
        try:
            restart_path = root / "logs" / "restart-server.json"
            if restart_path.exists() and json.loads(restart_path.read_text()).get("status") in {"starting", "restarting"}:
                raise RuntimeError("Server restart is pending")
        except BaseException:
            lock.release()
            raise
    try:
        games = inventory(root, database)
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        progress = {"run_id": run_id, "pid": os.getpid(), "status": "running", "depth": depth,
                    "workers": workers, "mode": "refresh-labels" if refresh else "backfill", "total": len(games), "done": 0, "written": 0, "existing": 0,
                    "failed": {}, "sources": {}, "games": {}, "started_at": datetime.now(timezone.utc).isoformat()}
        for state, directory, source in games.values():
            progress["sources"][source] = progress["sources"].get(source, 0) + 1
        path = root / "logs" / "annotation-backfill.json"
        if path.exists():
            shutil.copy2(path, root / "logs" / ("annotation-backfill-before-" + run_id + ".json"))
        write_progress(path, progress)
        # Short games first: make useful saved annotations available quickly.
        priority = priority or []
        ordered = sorted(games.items(), key=lambda pair: (0 if pair[0] in priority else 1, len(pair[1][0].get("moves") or [])))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(backfill_game, state, directory, run_id, depth, refresh=refresh): game_id
                       for game_id, (state, directory, source) in ordered}
            for future in as_completed(futures):
                game_id = futures[future]
                try:
                    result = future.result()
                    progress[result] += 1
                    progress["games"][game_id] = result
                except Exception as error:
                    progress["failed"][game_id] = str(error)
                    progress["games"][game_id] = "failed"
                progress["done"] += 1
                progress["updated_at"] = datetime.now(timezone.utc).isoformat()
                write_progress(path, progress)
        progress.update(status="complete" if not progress["failed"] else "complete_with_errors",
                        finished_at=datetime.now(timezone.utc).isoformat())
        write_progress(path, progress)
        return progress
    finally:
        lock.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=resolve_base_dir())
    parser.add_argument("--database", type=Path, default=resolve_finished_games_db())
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--depth", type=int)
    parser.add_argument("--refresh-labels", action="store_true", help="Reuse saved evaluations; reverify move annotations")
    parser.add_argument("--priority-game", action="append", default=[], help="Refresh a cited game before the rest of the archive")
    args = parser.parse_args()
    if args.depth is not None and not 1 <= args.depth <= 40: parser.error("depth must be between 1 and 40")
    result = run(args.root, args.database, args.workers, args.depth, args.refresh_labels, args.priority_game)
    print(json.dumps({key: result[key] for key in ("status", "total", "written", "existing", "failed")}))
