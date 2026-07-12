"""Per-engine continuous calibration tied to the spectator process lifetime."""

from __future__ import annotations

import asyncio
import math
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .calibration_view import (
    DEFAULT_FLOATING_ELO,
    calibrated_elo_for,
    invalidate_merge_cache,
    merge_calibration_ratings,
    rebuild_merged_ratings_file,
)
from .opponents import Opponent, OpponentCatalog, get_catalog
from .paths import project_root

_CAL_ROOT = project_root() / "elo_calibration"
if str(_CAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_CAL_ROOT))

from calibration.play_config import MatchConfig, PlayConfig  # noqa: E402
from calibration.ratings import CalibrationLadder, is_anchor  # noqa: E402
from calibration.worker import play_resilient_match_worker  # noqa: E402

CONTINUOUS_SUITE = "continuous"
DEFAULT_MOVETIME_MS = 100
DEFAULT_MAX_PLIES = 200
MATCH_SIGMA_ELO = 400.0
MAX_PARALLEL_GAMES = 100
SAVE_DEBOUNCE_SEC = 1.0
PROCESS_POOL_WORKERS = max(1, min(os.cpu_count() or 4, MAX_PARALLEL_GAMES))


def clamp_parallel(parallel: int) -> int:
    return max(1, min(MAX_PARALLEL_GAMES, int(parallel)))


def _results_dir() -> Path:
    return _CAL_ROOT / "results" / CONTINUOUS_SUITE


def _ratings_path() -> Path:
    return _results_dir() / "ratings.json"


def _games_log_path() -> Path:
    return _results_dir() / "games.jsonl"


def display_elo(opp: Opponent, calibration: Dict[str, Dict[str, Any]]) -> float:
    if opp.type == "stockfish":
        return float(opp.elo)
    row = calibration.get(opp.id)
    if row and row.get("games", 0) > 0:
        return float(row["elo"])
    cal = calibrated_elo_for(opp, calibration)
    if cal is not None:
        return float(cal)
    return float(opp.elo if opp.elo else DEFAULT_FLOATING_ELO)


def pick_similar_opponent(
    focus_id: str,
    catalog: Optional[OpponentCatalog] = None,
    calibration: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    rng: Optional[random.Random] = None,
    sigma_elo: Optional[float] = None,
    min_weight: Optional[float] = None,
) -> str:
    """Random playable opponent near focus calibrated ELO, never the focus engine itself."""
    cat = catalog or get_catalog()
    cal = calibration if calibration is not None else merge_calibration_ratings()
    focus = cat.get(focus_id)
    focus_elo = display_elo(focus, cal)
    matching = cat.matching
    sigma = float(
        sigma_elo if sigma_elo is not None else matching.get("sigma_elo", MATCH_SIGMA_ELO)
    )
    floor_w = float(
        min_weight if min_weight is not None else matching.get("min_weight", 0.08)
    )

    candidates: List[Opponent] = []
    weights: List[float] = []
    for opp in cat.list_opponents():
        if opp.id == focus_id:
            continue
        if is_anchor(opp):
            continue
        if not cat._is_playable(opp):
            continue
        opp_elo = display_elo(opp, cal)
        delta = abs(opp_elo - focus_elo)
        weights.append(max(floor_w, math.exp(-delta / sigma)))
        candidates.append(opp)

    if not candidates:
        raise RuntimeError(f"No calibration opponents available for {focus_id}")

    r = rng or random.Random()
    return r.choices(candidates, weights=weights, k=1)[0].id


def play_config_for(opponent_id: str, catalog: Optional[OpponentCatalog] = None) -> PlayConfig:
    opp = (catalog or get_catalog()).get(opponent_id)
    if opp.type == "random":
        return PlayConfig(movetime_ms=DEFAULT_MOVETIME_MS)
    cfg = PlayConfig(movetime_ms=DEFAULT_MOVETIME_MS)
    if opp.harness:
        h = opp.harness
        cfg = PlayConfig(
            movetime_ms=int(h.get("movetime_ms", DEFAULT_MOVETIME_MS)),
            depth=int(h["depth"]) if h.get("depth") is not None else None,
            random_move_pct=float(h.get("random_move_pct", 0.0)),
        )
    return cfg


def build_random_match(focus_id: str, opponent_id: str, *, rng: Optional[random.Random] = None) -> MatchConfig:
    r = rng or random.Random()
    cat = get_catalog()
    if r.random() < 0.5:
        white_id, black_id = focus_id, opponent_id
    else:
        white_id, black_id = opponent_id, focus_id
    return MatchConfig(
        white_id=white_id,
        black_id=black_id,
        max_plies=DEFAULT_MAX_PLIES,
        start_fen="startpos",
        white=play_config_for(white_id, cat),
        black=play_config_for(black_id, cat),
    )


def can_continuously_calibrate(opponent_id: str, catalog: Optional[OpponentCatalog] = None) -> bool:
    opp = (catalog or get_catalog()).get(opponent_id)
    return not is_anchor(opp)


class ContinuousCalibrationManager:
    """Runs per-engine calibration loops while the spectator server is up."""

    def __init__(self) -> None:
        self._tasks: Dict[str, List[asyncio.Task]] = {}
        self._stop_events: Dict[str, asyncio.Event] = {}
        self._active_engines: Set[str] = set()
        self._parallel: Dict[str, int] = {}
        self._in_flight: Dict[str, int] = {}
        self._recent_games: List[Dict[str, Any]] = []
        self._skipped_games = 0
        self._lock = asyncio.Lock()
        self._ladder = self._load_ladder()
        self._executor: Optional[ProcessPoolExecutor] = None
        self._dirty = False
        self._flush_task: Optional[asyncio.Task] = None

    def _ensure_executor(self) -> ProcessPoolExecutor:
        if self._executor is None:
            self._executor = ProcessPoolExecutor(max_workers=PROCESS_POOL_WORKERS)
        return self._executor

    def _load_ladder(self) -> CalibrationLadder:
        """Seed from best-known ratings across all suites (never reset to 500 if ladder data exists)."""
        ladder = CalibrationLadder()
        for oid, row in merge_calibration_ratings().items():
            ladder.ratings[oid] = float(row.get("elo_exact", row["elo"]))
            ladder.games_played[oid] = int(row.get("games", 0))

        path = _ratings_path()
        if path.exists():
            saved = CalibrationLadder.load(path)
            for oid, elo in saved.ratings.items():
                saved_games = int(saved.games_played.get(oid, 0))
                if saved_games > ladder.games_played.get(oid, 0):
                    ladder.ratings[oid] = elo
                    ladder.games_played[oid] = saved_games
        return ladder

    def _persist_ladder(self) -> None:
        self._ladder.save(_ratings_path())
        rebuild_merged_ratings_file()
        invalidate_merge_cache()

    async def _schedule_save(self) -> None:
        self._dirty = True
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._debounced_flush())

    async def _debounced_flush(self) -> None:
        await asyncio.sleep(SAVE_DEBOUNCE_SEC)
        async with self._lock:
            if self._dirty:
                await asyncio.to_thread(self._persist_ladder)
                self._dirty = False

    async def _flush_saves_now(self) -> None:
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        async with self._lock:
            if self._dirty:
                await asyncio.to_thread(self._persist_ladder)
                self._dirty = False

    def is_running(self, engine_id: str) -> bool:
        return engine_id in self._active_engines

    def running_engines(self) -> Set[str]:
        return set(self._active_engines)

    async def start(self, engine_id: str, *, parallel: int = 1) -> None:
        if not can_continuously_calibrate(engine_id):
            raise ValueError(f"Cannot continuously calibrate anchor engine: {engine_id}")
        if self.is_running(engine_id):
            return
        workers = clamp_parallel(parallel)
        self._ensure_executor()
        self._active_engines.add(engine_id)
        self._parallel[engine_id] = workers
        self._stop_events[engine_id] = asyncio.Event()
        self._tasks[engine_id] = [
            asyncio.create_task(self._run_loop(engine_id)) for _ in range(workers)
        ]

    async def stop(self, engine_id: str) -> None:
        self._active_engines.discard(engine_id)
        self._parallel.pop(engine_id, None)
        self._in_flight.pop(engine_id, None)
        event = self._stop_events.pop(engine_id, None)
        if event:
            event.set()
        tasks = self._tasks.pop(engine_id, [])
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self) -> None:
        for engine_id in list(self._active_engines):
            await self.stop(engine_id)
        await self._flush_saves_now()
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

    def _bump_in_flight(self, white_id: str, black_id: str, delta: int) -> None:
        for oid in (white_id, black_id):
            if delta > 0:
                self._in_flight[oid] = self._in_flight.get(oid, 0) + delta
            else:
                cur = self._in_flight.get(oid, 0) + delta
                if cur <= 0:
                    self._in_flight.pop(oid, None)
                else:
                    self._in_flight[oid] = cur

    def _record_recent(
        self,
        *,
        game_index: int,
        white: str,
        black: str,
        result: str,
        updates: List[Dict[str, Any]],
        skipped: bool = False,
    ) -> None:
        entry = {
            "game_index": game_index,
            "white": white,
            "black": black,
            "result": result,
            "updates": updates,
            "skipped": skipped,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self._recent_games.append(entry)
        self._recent_games = self._recent_games[-30:]

    async def _play_match_in_pool(self, match: MatchConfig) -> Optional[str]:
        loop = asyncio.get_running_loop()
        outcome = await loop.run_in_executor(
            self._ensure_executor(),
            play_resilient_match_worker,
            match.to_dict(),
        )
        return outcome.get("result")

    async def _run_loop(self, engine_id: str) -> None:
        stop = self._stop_events[engine_id]
        rng = random.Random()
        try:
            while not stop.is_set():
                try:
                    opponent_id = pick_similar_opponent(engine_id, rng=rng)
                except RuntimeError:
                    await asyncio.sleep(2.0)
                    continue

                if stop.is_set():
                    break

                match = build_random_match(engine_id, opponent_id, rng=rng)
                self._bump_in_flight(match.white_id, match.black_id, 1)
                try:
                    result = await self._play_match_in_pool(match)
                except asyncio.CancelledError:
                    raise
                finally:
                    self._bump_in_flight(match.white_id, match.black_id, -1)

                if stop.is_set():
                    break

                if result is None:
                    self._skipped_games += 1
                    self._record_recent(
                        game_index=0,
                        white=match.white_id,
                        black=match.black_id,
                        result="skipped (timeout)",
                        updates=[],
                        skipped=True,
                    )
                    await asyncio.sleep(0.5)
                    continue

                async with self._lock:
                    self._ladder.ensure_player(match.white_id)
                    self._ladder.ensure_player(match.black_id)
                    record = self._ladder.record_game(match.white_id, match.black_id, result)
                    self._ladder.append_game_log(_games_log_path(), record)
                    updates = [
                        {
                            "opponent_id": u.opponent_id,
                            "elo_before": round(u.elo_before, 1),
                            "elo_after": round(u.elo_after, 1),
                            "elo_delta": round(u.elo_delta, 1),
                        }
                        for u in record.updates
                    ]
                    self._record_recent(
                        game_index=record.game_index,
                        white=match.white_id,
                        black=match.black_id,
                        result=result,
                        updates=updates,
                    )
                    await self._schedule_save()
        except asyncio.CancelledError:
            pass
        finally:
            current = asyncio.current_task()
            workers = self._tasks.get(engine_id, [])
            if workers:
                remaining = [t for t in workers if t is not current and not t.done()]
                if remaining:
                    self._tasks[engine_id] = remaining
                else:
                    self._tasks.pop(engine_id, None)
                    if engine_id in self._active_engines:
                        self._active_engines.discard(engine_id)
                        self._parallel.pop(engine_id, None)
                        self._stop_events.pop(engine_id, None)
                        self._in_flight.pop(engine_id, None)

    def status_payload(self) -> Dict[str, Any]:
        running = self.running_engines()
        return {
            "mode": "continuous",
            "active": bool(running),
            "continuous_engines": sorted(running),
            "parallel_by_engine": dict(self._parallel),
            "process_pool_workers": PROCESS_POOL_WORKERS,
            "skipped_games": self._skipped_games,
            "in_flight_by_engine": dict(self._in_flight),
            "recent_games": list(self._recent_games),
            "rating_table": self._ladder.rating_table(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def enrich_rating_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        running = self.running_engines()
        in_flight = self._in_flight
        enriched: List[Dict[str, Any]] = []
        for row in rows:
            copy = dict(row)
            if copy.get("anchor"):
                copy["continuous"] = False
                copy["can_calibrate"] = False
                copy["playing"] = 0
                copy["activity"] = "anchor"
            else:
                eid = copy["id"]
                copy["can_calibrate"] = True
                copy["continuous"] = eid in running
                copy["parallel"] = int(self._parallel.get(eid, 1))
                playing = int(in_flight.get(eid, 0))
                copy["playing"] = playing
                if playing > 0:
                    copy["activity"] = "playing"
                elif copy["continuous"]:
                    copy["activity"] = "continuous"
                else:
                    copy["activity"] = "idle"
            enriched.append(copy)
        return enriched


_manager: Optional[ContinuousCalibrationManager] = None


def get_continuous_calibration() -> ContinuousCalibrationManager:
    global _manager
    if _manager is None:
        _manager = ContinuousCalibrationManager()
    return _manager
