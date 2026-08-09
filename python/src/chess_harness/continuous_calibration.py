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

from .play_rating import process_calibration_game_quality

CONTINUOUS_SUITE = "continuous"
DEFAULT_MOVETIME_MS = 100
DEFAULT_MAX_PLIES = 200
MATCH_SIGMA_ELO = 400.0
MAX_PARALLEL_GAMES = 100
SAVE_DEBOUNCE_SEC = 1.0
PROCESS_POOL_WORKERS = max(1, min(os.cpu_count() or 4, MAX_PARALLEL_GAMES))

PAIRING_MODES = ("floaters", "random", "anchors", "anchors-self", "fixed")
DEFAULT_PAIRING_MODE = "floaters"


def normalize_pairing_mode(mode: str) -> str:
    m = (mode or DEFAULT_PAIRING_MODE).strip().lower()
    if m not in PAIRING_MODES:
        raise ValueError(f"pairing_mode must be one of: {', '.join(PAIRING_MODES)}")
    return m


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


def pick_opponent(
    focus_id: str,
    catalog: Optional[OpponentCatalog] = None,
    calibration: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    pairing_mode: str = DEFAULT_PAIRING_MODE,
    fixed_opponent_id: Optional[str] = None,
    rng: Optional[random.Random] = None,
    sigma_elo: Optional[float] = None,
    min_weight: Optional[float] = None,
) -> str:
    """Pick an opponent for continuous calibration under the global pairing mode."""
    mode = normalize_pairing_mode(pairing_mode)
    cat = catalog or get_catalog()

    if mode == "fixed":
        oid = (fixed_opponent_id or "").strip()
        if not oid:
            raise RuntimeError("No fixed opponent selected")
        if oid == focus_id:
            raise RuntimeError(f"Cannot pair {focus_id} with itself")
        opp = cat.get(oid)
        if not opp.enabled or not cat._is_playable(opp):
            raise RuntimeError(f"Fixed opponent not playable: {oid}")
        return oid

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
        if not opp.enabled:
            continue
        if not cat._is_playable(opp):
            continue
        if mode == "floaters" and is_anchor(opp):
            continue
        if mode in ("anchors", "anchors-self") and not is_anchor(opp):
            continue
        if mode == "floaters":
            opp_elo = display_elo(opp, cal)
            delta = abs(opp_elo - focus_elo)
            max_delta = matching.get("max_delta_elo")
            if max_delta is not None and delta > float(max_delta):
                continue
            candidates.append(opp)
            weights.append(max(floor_w, math.exp(-delta / sigma)))
        else:
            candidates.append(opp)
            weights.append(1.0)

    if not candidates:
        raise RuntimeError(f"No calibration opponents available for {focus_id} ({mode})")

    r = rng or random.Random()
    if mode == "floaters":
        return r.choices(candidates, weights=weights, k=1)[0].id
    return r.choices(candidates, weights=weights, k=1)[0].id


def pick_similar_opponent(
    focus_id: str,
    catalog: Optional[OpponentCatalog] = None,
    calibration: Optional[Dict[str, Dict[str, Any]]] = None,
    *,
    rng: Optional[random.Random] = None,
    sigma_elo: Optional[float] = None,
    min_weight: Optional[float] = None,
) -> str:
    """Backward-compatible alias: ELO-weighted floaters only."""
    return pick_opponent(
        focus_id,
        catalog,
        calibration,
        pairing_mode="floaters",
        rng=rng,
        sigma_elo=sigma_elo,
        min_weight=min_weight,
    )


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
    for oid in (focus_id, opponent_id):
        opp = cat.get(oid)
        if not opp.enabled or not cat._is_playable(opp):
            raise ValueError(f"Opponent not playable for calibration: {oid}")
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


def can_continuously_calibrate(
    opponent_id: str,
    catalog: Optional[OpponentCatalog] = None,
    *,
    pairing_mode: Optional[str] = None,
) -> bool:
    """Whether an engine may run continuous games.

    Anchors are read-only reference tiers — they only run when the pairing
    mode is ``anchors-self`` (anchors between themselves).
    """
    cat = catalog or get_catalog()
    opp = cat.get(opponent_id)
    if is_anchor(opp):
        return pairing_mode == "anchors-self"
    return pairing_mode != "anchors-self" and opp.enabled and cat._is_playable(opp)


def list_calibratable_engine_ids(
    catalog: Optional[OpponentCatalog] = None,
    *,
    pairing_mode: Optional[str] = None,
) -> List[str]:
    cat = catalog or get_catalog()
    return [
        o.id
        for o in cat.list_opponents()
        if can_continuously_calibrate(o.id, cat, pairing_mode=pairing_mode)
    ]


def list_pairing_opponent_choices(catalog: Optional[OpponentCatalog] = None) -> List[Dict[str, str]]:
    cat = catalog or get_catalog()
    choices: List[Dict[str, str]] = []
    for opp in cat.list_opponents():
        if not opp.enabled or not cat._is_playable(opp):
            continue
        choices.append({"id": opp.id, "label": opp.format_label()})
    return choices


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
        self._quality_sem = asyncio.Semaphore(max(1, min(4, (os.cpu_count() or 4) // 2)))
        self._ladder = self._load_ladder()
        self._executor: Optional[ProcessPoolExecutor] = None
        self._dirty = False
        self._flush_task: Optional[asyncio.Task] = None
        self._pairing_mode = DEFAULT_PAIRING_MODE
        self._fixed_opponent_id: Optional[str] = "stockfish:0"

    async def _run_quality_job(
        self,
        record: Any,
        white_id: str,
        black_id: str,
        uci_moves: List[str],
    ) -> None:
        """Analyse moves for play-rating samples; never holds the ladder lock."""
        try:
            async with self._quality_sem:
                await asyncio.to_thread(
                    process_calibration_game_quality,
                    record,
                    white_id,
                    black_id,
                    uci_moves,
                )
        except Exception:
            return

    def pairing_mode(self) -> str:
        return self._pairing_mode

    def fixed_opponent_id(self) -> Optional[str]:
        return self._fixed_opponent_id

    def set_pairing_mode(self, mode: str) -> str:
        self._pairing_mode = normalize_pairing_mode(mode)
        return self._pairing_mode

    def set_fixed_opponent(self, opponent_id: str) -> str:
        cat = get_catalog()
        opp = cat.get(opponent_id)
        if not opp.enabled or not cat._is_playable(opp):
            raise ValueError(f"Opponent not playable: {opponent_id}")
        self._fixed_opponent_id = opponent_id
        return opponent_id

    def _ensure_executor(self) -> ProcessPoolExecutor:
        if self._executor is None:
            self._executor = ProcessPoolExecutor(
                max_workers=PROCESS_POOL_WORKERS,
                max_tasks_per_child=1,
            )
        return self._executor

    async def _shutdown_executor(self) -> None:
        if self._executor is not None:
            loop = asyncio.get_running_loop()
            executor = self._executor
            self._executor = None
            # Don't block Stop all on draining in-flight pool workers.
            await loop.run_in_executor(
                None,
                lambda: executor.shutdown(wait=False, cancel_futures=True),
            )

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
        ladder.prune_removed_opponents()
        return ladder

    def _persist_ladder(self) -> None:
        self._ladder.save(_ratings_path())
        rebuild_merged_ratings_file()
        invalidate_merge_cache()
        from .snapshot_leaderboard import request_public_snapshots_refresh

        request_public_snapshots_refresh()

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

    async def start_all(self, *, parallel: int = 1) -> List[str]:
        started: List[str] = []
        for engine_id in list_calibratable_engine_ids(pairing_mode=self._pairing_mode):
            if self.is_running(engine_id):
                continue
            await self.start(engine_id, parallel=parallel)
            started.append(engine_id)
        return started

    async def start(self, engine_id: str, *, parallel: int = 1) -> None:
        if not can_continuously_calibrate(engine_id, pairing_mode=self._pairing_mode):
            raise ValueError(f"Cannot continuously calibrate engine: {engine_id}")
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
        if not self._active_engines:
            await self._shutdown_executor()

    async def stop_running_engines(self) -> List[str]:
        """Stop all continuous loops and tear down the process pool."""
        stopped = list(self._active_engines)
        for engine_id in stopped:
            await self.stop(engine_id)
        await self._flush_saves_now()
        await self._shutdown_executor()
        return stopped

    async def stop_all(self) -> List[str]:
        stopped = list(self._active_engines)
        for engine_id in stopped:
            await self.stop(engine_id)
        await self._flush_saves_now()
        await self._shutdown_executor()
        return stopped

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

    async def _play_match_in_pool(self, match: MatchConfig) -> Dict[str, Any]:
        loop = asyncio.get_running_loop()
        outcome = await loop.run_in_executor(
            self._ensure_executor(),
            play_resilient_match_worker,
            match.to_dict(),
        )
        return outcome

    async def _run_loop(self, engine_id: str) -> None:
        stop = self._stop_events[engine_id]
        rng = random.Random()
        try:
            while not stop.is_set():
                try:
                    opponent_id = pick_opponent(
                        engine_id,
                        pairing_mode=self._pairing_mode,
                        fixed_opponent_id=self._fixed_opponent_id,
                        rng=rng,
                    )
                except RuntimeError:
                    await asyncio.sleep(2.0)
                    continue

                if stop.is_set():
                    break

                match = build_random_match(engine_id, opponent_id, rng=rng)
                self._bump_in_flight(match.white_id, match.black_id, 1)
                try:
                    outcome = await self._play_match_in_pool(match)
                except asyncio.CancelledError:
                    raise
                finally:
                    self._bump_in_flight(match.white_id, match.black_id, -1)

                if stop.is_set():
                    break

                result = outcome.get("result")
                uci_moves = outcome.get("uci_moves") or []

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

                # Keep the ladder lock short: only mutate in-memory ratings.
                # File I/O and quality analysis outside — otherwise engines stall at "0 live".
                quality_job: Optional[tuple] = None
                log_record = None
                log_moves: Optional[List[str]] = None
                async with self._lock:
                    self._ladder.ensure_player(match.white_id)
                    self._ladder.ensure_player(match.black_id)
                    record = self._ladder.record_game(match.white_id, match.black_id, result)
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
                    log_record = record
                    log_moves = list(uci_moves) if uci_moves else None
                    if uci_moves:
                        quality_job = (record, match.white_id, match.black_id, list(uci_moves))
                    self._dirty = True

                if log_record is not None:
                    await asyncio.to_thread(
                        self._ladder.append_game_log,
                        _games_log_path(),
                        log_record,
                        uci_moves=log_moves,
                    )
                    await self._schedule_save()

                if quality_job is not None:
                    asyncio.create_task(self._run_quality_job(*quality_job))
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
            "pairing_mode": self._pairing_mode,
            "fixed_opponent_id": self._fixed_opponent_id,
            "pairing_opponents": list_pairing_opponent_choices(),
            "calibratable_engines": list_calibratable_engine_ids(
                pairing_mode=self._pairing_mode
            ),
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
            if copy.get("anchor") and self._pairing_mode != "anchors-self":
                copy["continuous"] = False
                copy["can_calibrate"] = False
                copy["playing"] = 0
                copy["activity"] = "anchor"
                enriched.append(copy)
                continue
            eid = copy["id"]
            copy["can_calibrate"] = bool(copy.get("enabled", True))
            copy["continuous"] = eid in running
            copy["parallel"] = int(self._parallel.get(eid, 1))
            playing = int(in_flight.get(eid, 0))
            copy["playing"] = playing
            if playing > 0:
                copy["activity"] = "playing"
            elif copy["continuous"]:
                copy["activity"] = "continuous"
            elif not copy.get("enabled", True):
                copy["activity"] = "disabled"
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
