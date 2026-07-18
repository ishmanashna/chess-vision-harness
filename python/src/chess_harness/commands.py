"""Shared command handlers for chess-harness CLI."""

from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, List, Optional

from .board_controller import BoardController
from .elo import ELOLadder
from .engine import OpponentEngineManager
from .game_manager import GameManager
from .ladder_display import format_agent_leaderboard_cli, format_opponent_ladder_cli
from .opponents import get_catalog
from .results import ResultsManager
from .models import ModelRegistry, format_model_list
from .tournament import TournamentManager


def _game_manager() -> GameManager:
    return GameManager()


def _with_controller() -> BoardController:
    gm = _game_manager()
    return BoardController(gm)


def _without_engine() -> BoardController:
    return _with_controller()


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


def _prune_idle_games() -> None:
    _without_engine().check_idle_games()


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
    _prune_idle_games()
    ctrl = _with_controller()
    try:
        return ctrl.new_game(
            game_id,
            color,
            fen=fen,
            model_name=model_name,
            force=force,
            opponent_id=opponent,
            skill=skill,
        )
    finally:
        ctrl.opponent_mgr.release()
        if ctrl._eval_engine is not None:
            ctrl._eval_engine.quit()
            ctrl._eval_engine = None


def cmd_move(game_id: str, move_str: str) -> Dict[str, Any]:
    _prune_idle_games()
    ctrl = _with_controller()
    try:
        return ctrl.make_agent_move(game_id, move_str)
    finally:
        ctrl.opponent_mgr.release()
        if ctrl._eval_engine is not None:
            ctrl._eval_engine.quit()
            ctrl._eval_engine = None


def cmd_board(game_id: str) -> Dict[str, Any]:
    return _without_engine().get_board(game_id)


def cmd_pgn(game_id: str) -> Dict[str, Any]:
    return _without_engine().export_pgn(game_id)


def cmd_game_audit(game_id: str) -> Dict[str, Any]:
    return _without_engine().game_audit(game_id)


def cmd_resign(game_id: str) -> Dict[str, Any]:
    return _without_engine().resign(game_id)


def cmd_status(game_id: str) -> Dict[str, Any]:
    return _without_engine().status(game_id)


def cmd_list() -> None:
    _prune_idle_games()
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

    os.environ.setdefault("CHESS_HARNESS_DEBUG", "1")
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


def default_game_id() -> str:
    return f"game-{os.getpid()}-{random.randint(1000, 9999)}"
