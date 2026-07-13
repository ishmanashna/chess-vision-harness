"""Orchestrate calibration schedules and optional engine matches."""

from __future__ import annotations

import random
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import chess
import yaml

from .game_loop import play_game
from .live import (
    clear_live_session,
    read_live_session,
    write_live_session,
    write_merged_ratings,
)
from .play_config import MatchConfig, PlayConfig
from .ratings import CalibrationLadder
from .report import write_report
from .worker import play_match_worker


def _catalog_opponent_enabled(opponent_id: str) -> bool:
    try:
        from chess_harness.opponents import get_catalog

        return get_catalog().get(opponent_id).enabled
    except (ValueError, ImportError):
        return True


def _match_playable(match: MatchConfig) -> bool:
    return _catalog_opponent_enabled(match.white_id) and _catalog_opponent_enabled(
        match.black_id
    )


def _load_suite(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _opening_fen(name: str) -> str:
    if name == "startpos":
        return chess.STARTING_FEN
    return name


def _default_play(suite: Dict[str, Any]) -> PlayConfig:
    defaults = suite.get("defaults", {})
    return PlayConfig(
        movetime_ms=int(defaults.get("movetime_ms", suite.get("movetime_ms", 100))),
        depth=defaults.get("depth", suite.get("depth")),
        random_move_pct=float(defaults.get("random_move_pct", 0.0)),
    )


def build_schedule(suite: Dict[str, Any], *, seed: int = 42) -> List[MatchConfig]:
    """Expand suite YAML into individual games (no engines started)."""
    rng = random.Random(seed)
    defaults = suite.get("defaults", {})
    default_play = _default_play(suite)
    max_plies = int(defaults.get("max_plies", suite.get("max_plies", 200)))
    openings = suite.get("openings", ["startpos"])
    schedule: List[MatchConfig] = []

    def side_config(pair: Dict[str, Any], side: str) -> PlayConfig:
        harness_key = f"{side}_harness"
        return PlayConfig.from_dict(pair.get(harness_key), default_play)

    for pair in suite.get("pairs", []):
        white_id = pair["white"]
        black_id = pair["black"]
        games = int(pair.get("games", 1))
        alternate = pair.get("colors") == "alternate"
        for i in range(games):
            w, b = (black_id, white_id) if alternate and i % 2 else (white_id, black_id)
            fen_name = rng.choice(openings)
            schedule.append(
                MatchConfig(
                    white_id=w,
                    black_id=b,
                    max_plies=max_plies,
                    start_fen=fen_name,
                    white=side_config(pair, "white"),
                    black=side_config(pair, "black"),
                )
            )

    rr = suite.get("round_robin")
    if rr:
        opponents = [o for o in rr["opponents"] if _catalog_opponent_enabled(o)]
        games_per_pair = int(rr.get("games_per_pair", 1))
        alternate = rr.get("colors") == "alternate"
        for i, a in enumerate(opponents):
            for b in opponents[i + 1 :]:
                for g in range(games_per_pair):
                    w, bl = (b, a) if alternate and g % 2 else (a, b)
                    fen_name = rng.choice(openings)
                    schedule.append(
                        MatchConfig(
                            white_id=w,
                            black_id=bl,
                            max_plies=max_plies,
                            start_fen=fen_name,
                            white=default_play,
                            black=default_play,
                        )
                    )

    return [m for m in schedule if _match_playable(m)]


def _init_ladder(suite: Dict[str, Any], schedule: List[MatchConfig]) -> CalibrationLadder:
    defaults = suite.get("defaults", {})
    ladder = CalibrationLadder(
        floating_start=float(defaults.get("initial_elo_non_stockfish", 500)),
        k_factor=int(defaults.get("k_factor", 48)),
    )
    for match in schedule:
        ladder.ensure_player(match.white_id)
        ladder.ensure_player(match.black_id)
    return ladder


def _project_root(results_dir: Path) -> Path:
    # <repo>/elo_calibration/results/<suite> -> repo root
    return results_dir.parent.parent.parent


def _in_flight_by_engine(matches: List[MatchConfig]) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    for match in matches:
        counts[match.white_id] += 1
        counts[match.black_id] += 1
    return dict(counts)


def _publish_live(
    project_root: Path,
    *,
    suite_name: str,
    workers: int,
    scheduled: int,
    completed: int,
    in_progress: int,
    ladder: CalibrationLadder,
    recent_games: List[Dict[str, Any]],
    active: bool,
    in_flight_by_engine: Optional[Dict[str, int]] = None,
) -> None:
    write_live_session(
        project_root,
        {
            "active": active,
            "suite": suite_name,
            "workers": workers,
            "scheduled": scheduled,
            "completed": completed,
            "in_progress": in_progress,
            "in_flight_by_engine": in_flight_by_engine or {},
            "rating_table": ladder.rating_table(),
            "recent_games": recent_games[-30:],
        },
    )
    write_merged_ratings(project_root, ladder.rating_table())


def _record_result(
    ladder: CalibrationLadder,
    games_log_path: Path,
    white_id: str,
    black_id: str,
    result: str,
    recent_games: List[Dict[str, Any]],
) -> None:
    record = ladder.record_game(white_id, black_id, result)
    ladder.append_game_log(games_log_path, record)
    recent_games.append(
        {
            "game_index": record.game_index,
            "white": white_id,
            "black": black_id,
            "result": result,
            "updates": [
                {
                    "opponent_id": u.opponent_id,
                    "elo_before": round(u.elo_before, 1),
                    "elo_after": round(u.elo_after, 1),
                    "elo_delta": round(u.elo_delta, 1),
                }
                for u in record.updates
            ],
        }
    )


def _play_sequential(
    schedule: List[MatchConfig],
    ladder: CalibrationLadder,
    games_log_path: Path,
    project_root: Path,
    suite_name: str,
) -> int:
    recent: List[Dict[str, Any]] = []
    _publish_live(
        project_root,
        suite_name=suite_name,
        workers=1,
        scheduled=len(schedule),
        completed=0,
        in_progress=1,
        ladder=ladder,
        recent_games=recent,
        active=True,
    )
    for i, match in enumerate(schedule):
        in_flight = {match.white_id: 1, match.black_id: 1}
        _publish_live(
            project_root,
            suite_name=suite_name,
            workers=1,
            scheduled=len(schedule),
            completed=i,
            in_progress=1,
            ladder=ladder,
            recent_games=recent,
            active=True,
            in_flight_by_engine=in_flight,
        )
        result = play_game(match)
        _record_result(ladder, games_log_path, match.white_id, match.black_id, result, recent)
        ladder.save(games_log_path.parent / "ratings.json")
        _publish_live(
            project_root,
            suite_name=suite_name,
            workers=1,
            scheduled=len(schedule),
            completed=i + 1,
            in_progress=0,
            ladder=ladder,
            recent_games=recent,
            active=True,
            in_flight_by_engine={},
        )
    return len(schedule)


def _play_parallel(
    schedule: List[MatchConfig],
    ladder: CalibrationLadder,
    games_log_path: Path,
    project_root: Path,
    suite_name: str,
    workers: int,
) -> int:
    recent: List[Dict[str, Any]] = []
    completed = 0
    pending = list(schedule)
    in_flight: List[MatchConfig] = []
    futures: Dict[Future, MatchConfig] = {}

    def publish() -> None:
        _publish_live(
            project_root,
            suite_name=suite_name,
            workers=workers,
            scheduled=len(schedule),
            completed=completed,
            in_progress=len(in_flight),
            ladder=ladder,
            recent_games=recent,
            active=True,
            in_flight_by_engine=_in_flight_by_engine(in_flight),
        )

    publish()

    with ProcessPoolExecutor(max_workers=workers) as executor:
        while pending or futures:
            while pending and len(futures) < workers:
                match = pending.pop(0)
                in_flight.append(match)
                futures[executor.submit(play_match_worker, match.to_dict())] = match
            if not futures:
                break
            done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                match = futures.pop(future)
                in_flight.remove(match)
                outcome = future.result()
                _record_result(
                    ladder,
                    games_log_path,
                    outcome["white_id"],
                    outcome["black_id"],
                    outcome["result"],
                    recent,
                )
                completed += 1
                ladder.save(games_log_path.parent / "ratings.json")
            publish()

    return completed


def run_suite(
    suite_path: Path,
    results_dir: Path,
    *,
    seed: int = 42,
    play: bool = False,
    reset_ratings: bool = False,
    workers: int = 1,
) -> Dict[str, Any]:
    suite = _load_suite(suite_path)
    schedule = build_schedule(suite, seed=seed)
    ratings_path = results_dir / "ratings.json"
    games_log_path = results_dir / "games.jsonl"
    project_root = _project_root(results_dir)
    suite_name = suite.get("name", suite_path.stem)
    workers = max(1, int(workers))

    if reset_ratings or not ratings_path.exists():
        ladder = _init_ladder(suite, schedule)
    else:
        ladder = CalibrationLadder.load(ratings_path)
        for match in schedule:
            ladder.ensure_player(match.white_id)
            ladder.ensure_player(match.black_id)

    games_played = 0
    if play:
        if games_log_path.exists() and reset_ratings:
            games_log_path.write_text("", encoding="utf-8")
        try:
            if workers == 1:
                games_played = _play_sequential(
                    schedule, ladder, games_log_path, project_root, suite_name
                )
            else:
                games_played = _play_parallel(
                    schedule, ladder, games_log_path, project_root, suite_name, workers
                )
        finally:
            ladder.save(ratings_path)
            write_merged_ratings(project_root, ladder.rating_table())
            _publish_live(
                project_root,
                suite_name=suite_name,
                workers=workers,
                scheduled=len(schedule),
                completed=games_played,
                in_progress=0,
                ladder=ladder,
                recent_games=read_live_session(project_root).get("recent_games", [])
                if read_live_session(project_root)
                else [],
                active=False,
                in_flight_by_engine={},
            )

    summary = {
        "suite": suite_name,
        "mode": "play" if play else "dry_run",
        "workers": workers,
        "scheduled_games": len(schedule),
        "games_played": games_played,
        "floating_start_elo": ladder.floating_start,
        "k_factor": ladder.k_factor,
        "rating_table": ladder.rating_table(),
        "stabilization": ladder.stabilization_hint(),
        "schedule_preview": [
            {
                "white": m.white_id,
                "black": m.black_id,
                "opening": m.start_fen,
                "white_harness": {
                    "movetime_ms": m.white.movetime_ms,
                    "depth": m.white.depth,
                    "random_move_pct": m.white.random_move_pct,
                },
                "black_harness": {
                    "movetime_ms": m.black.movetime_ms,
                    "depth": m.black.depth,
                    "random_move_pct": m.black.random_move_pct,
                },
            }
            for m in schedule[:10]
        ],
    }
    if len(schedule) > 10:
        summary["schedule_preview_note"] = f"Showing first 10 of {len(schedule)} games"

    write_report(results_dir, summary)
    return summary
