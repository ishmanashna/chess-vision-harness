"""Shared command handlers for chess-harness CLI."""

from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List, Optional

from .elo import ELOLadder
from .game_ids import new_game_id
from .game_manager import GameManager
from .game_service import GameService
from .ladder_display import format_agent_leaderboard_cli, format_opponent_ladder_cli
from .opponents import get_catalog
from .results import ResultsManager
from .models import ModelRegistry, format_model_list
from .tournament import TournamentManager


def _game_manager() -> GameManager:
    return GameManager()


def _game_service() -> GameService:
    return GameService(_game_manager())


def resolve_agent_color(color: Optional[str] = None) -> str:
    """Pick agent color. Default is random unless operator specifies white/black."""
    if color is None or str(color).lower() in ("random", ""):
        return random.choice(["white", "black"])
    normalized = str(color).lower()
    if normalized in ("white", "w"):
        return "white"
    if normalized in ("black", "b"):
        return "black"
    raise ValueError("agent_color must be 'white', 'black', or 'random'")


def cmd_new(
    game_id: str,
    color: Optional[str] = None,
    skill: Optional[int] = None,
    fen: Optional[str] = None,
    model_name: Optional[str] = None,
    force: bool = False,
    opponent: Optional[str] = None,
) -> Dict[str, Any]:
    color = resolve_agent_color(color)
    return _game_service().new_game(
        game_id,
        color,
        fen=fen,
        model_name=model_name,
        force=force,
        opponent_id=opponent,
        skill=skill,
    )


def cmd_move(game_id: str, move_str: str) -> Dict[str, Any]:
    return _game_service().make_move(game_id, move_str)


def cmd_board(game_id: str) -> Dict[str, Any]:
    return _game_service().get_board(game_id)


def cmd_imagine(game_id: str, moves: List[str]) -> Dict[str, Any]:
    """Write a hypothetical-line PNG outside the game dir; does not change state."""
    import tempfile
    from pathlib import Path

    result = _game_service().imagine_board(game_id, moves)
    if not result.get("ok"):
        return {k: v for k, v in result.items() if k != "png_bytes"}
    fd, path = tempfile.mkstemp(suffix=".png", prefix="chess-imagine-")
    os.close(fd)
    Path(path).write_bytes(result["png_bytes"])
    return {
        "ok": True,
        "game_id": game_id,
        "imagine_path": path,
        "applied_count": result.get("applied_count", 0),
        "hypothetical": True,
    }


def cmd_pgn(game_id: str) -> Dict[str, Any]:
    return _game_service().export_pgn(game_id)


def cmd_game_audit(game_id: str) -> Dict[str, Any]:
    return _game_service().game_audit(game_id)


def cmd_resign(game_id: str) -> Dict[str, Any]:
    return _game_service().resign(game_id)


def cmd_status(game_id: str) -> Dict[str, Any]:
    return _game_service().status(game_id)


def cmd_list() -> None:
    _game_service().prune_idle_games()
    gm = _game_manager()
    games = gm.list_games()
    if not games:
        print("No games found.")
        return
    for g in games:
        s = g["state"]
        opp = s.get("opponent_label") or s.get("opponent_id") or f"skill {s.get('skill')}"
        print(f"  {g['game_id']}: {s['agent_color']} vs {opp} - {s['status']}")


def cmd_opponents_list() -> None:
    catalog = get_catalog()
    for opp in catalog.list_opponents():
        if not opp.enabled:
            status = "disabled"
        elif catalog._is_playable(opp):
            status = "ok"
        else:
            status = "missing binary"
        print(f"  {opp.id}: {opp.format_label()} [{opp.type}, {status}]")


def cmd_opponents_set_enabled(opponent_id: str, enabled: bool) -> int:
    catalog = get_catalog()
    try:
        opp = catalog.set_enabled(opponent_id, enabled)
        state = "enabled" if opp.enabled else "disabled"
        print(f"Opponent {opp.id}: {state}")
        return 0
    except ValueError as e:
        print(str(e))
        return 1


def cmd_models_set_enabled(model_id: str, enabled: bool) -> int:
    registry = ModelRegistry()
    try:
        entry = registry.set_enabled(model_id, enabled)
        state = "enabled" if entry.get("enabled", True) else "disabled"
        print(f"Model {entry['id']}: {state}")
        return 0
    except ValueError as e:
        print(str(e))
        return 1


def cmd_opponents_verify() -> int:
    from .opponent_verify import verify_all_opponents

    return verify_all_opponents()


def cmd_leaderboard() -> None:
    ladder = ELOLadder(base_dir=str(_game_manager().base_dir))
    print(format_agent_leaderboard_cli(ladder))
    print(format_opponent_ladder_cli())


def cmd_snapshot_leaderboard(output: Optional[str] = None) -> None:
    from pathlib import Path

    from .snapshot_leaderboard import export_leaderboard_snapshot

    path = export_leaderboard_snapshot(Path(output) if output else None)
    print(f"Wrote leaderboard snapshot: {path}")


def cmd_models_list() -> None:
    print(format_model_list(ModelRegistry()))


def cmd_models_inscribe(model_id: str, name: Optional[str] = None) -> None:
    registry = ModelRegistry()
    try:
        entry = registry.inscribe(model_id, name)
        print(f"Inscribed: {entry['id']} ({entry['name']}) at {entry['elo']} ELO")
    except ValueError as e:
        print(str(e))


def cmd_models_uninscribe(model_id: str) -> int:
    registry = ModelRegistry()
    try:
        entry = registry.uninscribe(model_id)
        print(f"Removed: {entry['id']} ({entry.get('name', entry['id'])})")
        return 0
    except ValueError as e:
        print(str(e))
        return 1


def cmd_harness_reset(confirm: bool = False) -> int:
    from .harness_reset import harness_reset

    return harness_reset(confirm=confirm)


def cmd_migrate_results() -> int:
    """Normalize legacy model_name values in results.jsonl to canonical ids."""
    gm = _game_manager()
    registry = ModelRegistry()
    results_file = gm.results_file
    if not results_file.exists():
        print("No results.jsonl found.")
        return 0

    lines_out = []
    changed = 0
    for line in results_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        game = json.loads(line)
        raw = game.get("model_name")
        canonical = registry.normalize_result_model(raw)
        if canonical and canonical != raw:
            game["model_name"] = canonical
            changed += 1
        lines_out.append(json.dumps(game))

    results_file.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    print(f"Migrated {changed} result record(s) to canonical model ids.")
    return changed


def cmd_rating(model_name: str) -> None:
    ladder = ELOLadder(base_dir=str(_game_manager().base_dir))
    stats = ladder.get_stats(model_name)
    print(f"  {stats['name']} ({stats['model']}): {stats['elo']} ELO (rank {stats['rank']}/{stats['total_agents']})")


def cmd_aggregate() -> None:
    rm = ResultsManager(base_dir=str(_game_manager().base_dir))
    print(json.dumps(rm.get_summary(), indent=2))


def cmd_rebuild_elo() -> None:
    cmd_migrate_results()
    ladder = ELOLadder(base_dir=str(_game_manager().base_dir))
    ladder.process_results_file()
    print("ELO ratings rebuilt from results.jsonl")
    cmd_leaderboard()


def cmd_serve(host: str = "127.0.0.1", port: int = 8765, force: bool = False) -> None:
    import atexit

    import uvicorn

    from .serve_utils import ensure_port_available, remove_spectator_meta, write_spectator_meta
    from .spectator import app

    ensure_port_available(host, port, force=force)
    from .engine_cleanup import kill_orphaned_harness_processes

    killed = kill_orphaned_harness_processes()
    if killed:
        parts = ", ".join(f"{name}={count}" for name, count in killed.items())
        print(f"Cleaned up leftover processes from a previous session ({parts})")
    write_spectator_meta(host, port)
    atexit.register(remove_spectator_meta)

    print(f"Starting spectator on http://localhost:{port}")
    print("Stop with Ctrl+C, or run: chess-harness serve stop")
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    finally:
        remove_spectator_meta()


def cmd_serve_stop(port: int = 8765) -> None:
    from .engine_cleanup import kill_orphaned_harness_processes
    from .serve_utils import stop_spectator

    stop_spectator(port)
    killed = kill_orphaned_harness_processes()
    if killed:
        for name, count in killed.items():
            print(f"Killed orphaned {name}: {count}")


def cmd_tournament_create(
    opponents: List[str],
    games_per_cell: int = 1,
    prefix: str = "tour",
) -> Dict[str, Any]:
    # Tournament batch paths stay on BoardController until batch/HTTP diverge (Plan 0 defer).
    tm = TournamentManager(base_dir=str(_game_manager().base_dir))
    try:
        return tm.create_tournament_matrix(opponents, games_per_cell, prefix=prefix)
    finally:
        tm.controller.opponent_mgr.release()


def cmd_tournament_start(prefix: str = "tour") -> None:
    tm = TournamentManager(base_dir=str(_game_manager().base_dir))
    try:
        manifest = tm.load_manifest()
        if not manifest:
            print("No tournament manifest found. Run: chess-harness tournament create")
            return
        for game in manifest["games"]:
            if game.get("status") == "pending":
                result = tm.start_game(
                    game["game_id"], game["opponent_id"], game["agent_color"]
                )
                game["status"] = "started" if result.get("ok") else "failed"
                print(f"  {game['game_id']}: {result.get('ok', False)}")
    finally:
        tm.controller.opponent_mgr.release()


def cmd_tournament_smoke(num_games: int = 3, opponent: str = "stockfish:5") -> Dict[str, Any]:
    tm = TournamentManager(base_dir=str(_game_manager().base_dir))
    try:
        return tm.run_smoke_test(num_games=num_games, opponents=[opponent])
    finally:
        tm.controller.opponent_mgr.release()


def cmd_analyse_quality(
    game_id: Optional[str] = None,
    force: bool = False,
) -> int:
    """Re-analyse finished harness games from game.pgn (not calibration jsonl)."""
    from .quality_finish import run_game_quality

    gm = _game_manager()
    base = str(gm.base_dir)

    if game_id:
        candidates = [game_id]
    else:
        candidates = [
            g["game_id"]
            for g in gm.list_games(status_filter="finished")
            if g["state"].get("result") != "*"
            and gm.get_pgn_path(g["game_id"]).exists()
        ]

    analysed = 0
    skipped = 0
    failed = 0

    for gid in candidates:
        state = gm.load_state(gid)
        if not state or state.get("status") != "finished":
            print(f"  skip {gid}: not finished")
            skipped += 1
            continue
        if state.get("result") == "*":
            print(f"  skip {gid}: no result")
            skipped += 1
            continue
        if not gm.get_pgn_path(gid).exists():
            print(f"  skip {gid}: no game.pgn")
            skipped += 1
            continue
        if state.get("quality_at") and not force:
            print(f"  skip {gid}: already analysed (use --force to redo)")
            skipped += 1
            continue
        try:
            if run_game_quality(gid, base_dir=base, force=force):
                print(f"  ok {gid}")
                analysed += 1
            else:
                print(f"  skip {gid}: analysis did not complete")
                skipped += 1
        except Exception as exc:
            print(f"  fail {gid}: {exc}")
            failed += 1

    print(f"Quality backfill: {analysed} analysed, {skipped} skipped, {failed} failed")
    if analysed:
        from .snapshot_leaderboard import export_leaderboard_snapshot

        out = export_leaderboard_snapshot()
        print(f"Wrote leaderboard snapshot: {out}")
    return 1 if failed else 0


def cmd_prune_no_result(
    *,
    export_snapshot: bool = True,
    dry_run: bool = False,
) -> int:
    """Remove finished no-result games (PGN result *) and their results rows.

    Also scrubs orphan results.jsonl rows with no game directory when the row is a
    no-result (*). Rebuilds Elo after any removal so ladder state stays consistent
    if pruned games had ever carried deltas.

    Decisive results are never pruned — even when end_reason/reason is
    \"inactivity\" (legacy idle→resign games).
    """
    gm = _game_manager()
    rm = ResultsManager(base_dir=str(gm.base_dir))

    # Only true no-result rows (*). Do not delete decisive games that still carry
    # end_reason/reason "inactivity" from the legacy idle→resign path.
    candidates: List[str] = []
    for g in gm.list_games(status_filter="finished"):
        state = g["state"]
        if state.get("result") == "*":
            candidates.append(g["game_id"])

    candidate_set = set(candidates)
    orphan_ids: List[str] = []
    for row in rm.load_results():
        gid = row.get("game_id")
        if not gid or gid in candidate_set or gid in orphan_ids:
            continue
        if gm.game_exists(gid):
            continue
        if row.get("result") == "*":
            orphan_ids.append(gid)

    if not candidates and not orphan_ids:
        print("No no-result games to prune.")
        return 0

    removed = 0
    orphans_scrubbed = 0
    failed = 0
    for gid in sorted(candidates):
        if dry_run:
            print(f"  would remove {gid}")
            continue
        rows_removed = rm.remove_game_results(gid)
        if gm.delete_game(gid):
            print(f"  removed {gid} ({rows_removed} result row(s))")
            removed += 1
        else:
            print(f"  fail {gid}: could not delete game directory")
            failed += 1

    for gid in sorted(orphan_ids):
        if dry_run:
            print(f"  would scrub orphan results for {gid}")
            continue
        rows_removed = rm.remove_game_results(gid)
        print(f"  scrubbed orphan {gid} ({rows_removed} result row(s))")
        orphans_scrubbed += 1

    if dry_run:
        print("  would rebuild-elo")
        if export_snapshot:
            print("  would export leaderboard snapshot")
        print(
            f"Would prune {len(candidates)} no-result game(s)"
            f" and scrub {len(orphan_ids)} orphan result id(s) (dry run)"
        )
        return 0

    print(
        f"Pruned {removed} no-result game(s), scrubbed {orphans_scrubbed} orphan result id(s)"
    )
    if removed or orphans_scrubbed:
        cmd_rebuild_elo()
        if export_snapshot:
            from .snapshot_leaderboard import export_leaderboard_snapshot

            out = export_leaderboard_snapshot()
            print(f"Wrote leaderboard snapshot: {out}")
    return 1 if failed else 0


def cmd_remove_game(
    game_id: str,
    *,
    export_snapshot: bool = True,
    dry_run: bool = False,
) -> int:
    """Remove one game from results + disk, then rebuild Elo and leaderboard snapshot."""
    gm = _game_manager()
    if not gm.validate_game_id(game_id):
        print(f"Invalid game_id: {game_id}")
        return 1

    rm = ResultsManager(base_dir=str(gm.base_dir))
    dir_exists = gm.get_game_dir(game_id).exists()
    result_rows = sum(1 for row in rm.load_results() if row.get("game_id") == game_id)

    if not dir_exists and result_rows == 0:
        print(f"No game or results found for {game_id}")
        return 1

    if dry_run:
        if result_rows:
            print(f"  would remove {result_rows} result row(s) for {game_id}")
        if dir_exists:
            print(f"  would delete game directory {game_id}")
        print("  would rebuild-elo")
        if export_snapshot:
            print("  would export leaderboard snapshot")
        print(f"Would remove game {game_id} (dry run)")
        return 0

    rows_removed = rm.remove_game_results(game_id)
    print(f"  removed {rows_removed} result row(s) for {game_id}")

    if dir_exists:
        if gm.delete_game(game_id):
            print(f"  deleted game directory {game_id}")
        else:
            print(f"  fail {game_id}: could not delete game directory")
            return 1
    else:
        print(f"  no game directory for {game_id}")

    cmd_rebuild_elo()
    if export_snapshot:
        from .snapshot_leaderboard import export_leaderboard_snapshot

        out = export_leaderboard_snapshot()
        print(f"Wrote leaderboard snapshot: {out}")
    return 0


def cmd_rebuild_estimation_samples() -> int:
    """Rebuild play-rating samples from continuous games.jsonl uci_moves rows."""
    from .play_rating import rebuild_estimation_samples

    result = rebuild_estimation_samples()
    print(
        f"Rebuilt {result['samples']} samples from "
        f"{result['games_with_moves']} games with moves "
        f"({result['games_total']} total in log)"
    )
    return 0


def cmd_finished_db_import_live() -> int:
    """Import finished scored live games into ``data/finished_games.sqlite``."""
    from .finished_games_db import import_live_finished_games

    gm = _game_manager()
    rm = ResultsManager(base_dir=str(gm.base_dir))
    summary = import_live_finished_games(game_manager=gm, results_manager=rm)
    for gid in summary["game_ids"]:
        print(f"  upserted {gid}")
    print(
        f"Imported {summary['imported']} finished scored game(s) "
        f"(skipped {summary['skipped']} no-result) into {summary['db_path']}"
    )
    return 0


def cmd_finished_db_list() -> int:
    """List finished game ids in the permanent SQLite store."""
    from .finished_games_db import list_finished_games
    from .paths import resolve_finished_games_db

    rows = list_finished_games()
    if not rows:
        print(f"No finished games in {resolve_finished_games_db()}")
        return 0
    for row in rows:
        print(
            f"{row['game_id']}\t{row.get('result') or ''}\t"
            f"{row.get('finished_at') or ''}"
        )
    print(f"{len(rows)} game(s) in {resolve_finished_games_db()}")
    return 0


def cmd_finished_db_restore(
    game_id: str, *, export_snapshot: bool = True
) -> int:
    """Restore live game dir + missing results row from the finished-games DB."""
    from .finished_games_db import restore_finished_game

    gm = _game_manager()
    if not gm.validate_game_id(game_id):
        print(f"Invalid game_id: {game_id}")
        return 1

    rm = ResultsManager(base_dir=str(gm.base_dir))
    try:
        summary = restore_finished_game(
            game_id, game_manager=gm, results_manager=rm
        )
    except KeyError as exc:
        print(str(exc))
        return 1
    except OSError as exc:
        print(f"Restore failed: {exc}")
        return 1

    print(
        f"  restored games/{game_id}/ (state"
        f"{' + pgn' if summary['had_pgn'] else ''})"
    )
    print(f"  merged {summary['results_merged']} result row(s)")
    cmd_rebuild_elo()
    if export_snapshot:
        from .snapshot_leaderboard import export_leaderboard_snapshot

        out = export_leaderboard_snapshot()
        print(f"Wrote leaderboard snapshot: {out}")
    return 0


def default_game_id() -> str:
    return new_game_id()
