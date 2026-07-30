"""
Play-rating map: monotone Q → display strength (not ladder Elo).

Training samples come from continuous calibration floaters only.
Never calls CalibrationLadder.record_game or writes ratings.json.
"""

from __future__ import annotations

import json
import os
import statistics
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

import filelock

from .game_quality import SideQuality, analyse_game, composite_q_value
from .paths import project_root

CONTINUOUS_SUITE = "continuous"
Q_ALPHA = 8.0
Q_BETA = 25.0
MIN_MAP_SAMPLES = 30
MIN_GAMES_FOR_SAMPLE = 101
MAP_REFIT_DEBOUNCE_SEC = 1.0

_map_cache: Optional[Dict[str, Any]] = None
_map_cache_path: Optional[str] = None
_refit_timer: Optional[threading.Timer] = None
_refit_timer_lock = threading.Lock()


def continuous_results_dir(root: Optional[Path] = None) -> Path:
    base = root if root is not None else project_root() / "elo_calibration" / "results"
    return base / CONTINUOUS_SUITE


def samples_path(root: Optional[Path] = None) -> Path:
    return continuous_results_dir(root) / "play_rating_samples.jsonl"


def games_log_path(root: Optional[Path] = None) -> Path:
    return continuous_results_dir(root) / "games.jsonl"


def map_path(root: Optional[Path] = None) -> Path:
    return continuous_results_dir(root) / "play_rating_map.json"


def continuous_fit_lock_path(root: Optional[Path] = None) -> Path:
    """Shared lock for play_rating_map.json refits (legacy CLI/tests)."""
    return continuous_results_dir(root) / "continuous_fit"


@contextmanager
def _play_rating_lock(path: Path) -> Iterator[None]:
    lock = filelock.FileLock(str(path.with_suffix(path.suffix + ".lock")), timeout=30)
    lock.acquire()
    try:
        yield
    finally:
        if lock.is_locked:
            lock.release()


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON via temp + replace; Windows-safe retries if the target is briefly locked."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    last_err: Optional[BaseException] = None
    for attempt in range(12):
        try:
            os.replace(str(tmp), str(path))
            return
        except PermissionError as exc:
            last_err = exc
            time.sleep(0.05 * (attempt + 1))
        except OSError as exc:
            last_err = exc
            time.sleep(0.05 * (attempt + 1))
    # Fallback: in-place overwrite (callers hold the fit lock).
    try:
        path.write_text(text, encoding="utf-8")
        tmp.unlink(missing_ok=True)
    except OSError:
        tmp.unlink(missing_ok=True)
        if last_err is not None:
            raise last_err
        raise


def _read_json_object(path: Path) -> Optional[Dict[str, Any]]:
    """Load a JSON object; return None on missing, empty, or mid-write garbage."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def composite_q(side: SideQuality) -> Optional[float]:
    """Q = accuracy − α·normalized_acpl − β·blunder_rate."""
    return composite_q_value(side.accuracy, side.normalized_acpl, side.blunder_rate)


def is_sample_eligible(*, games_played: int, anchor: bool) -> bool:
    """Floaters with cumulative games_played >= 101 from the game record updates.

    Eligibility uses the ladder total at game time (after record_game), not a
    post-feature counter — engines already past 101 Elo games qualify as soon as
    moves are stored. Anchors never contribute samples.
    """
    if anchor:
        return False
    return games_played >= MIN_GAMES_FOR_SAMPLE


def load_samples(root: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = samples_path(root)
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_play_rating_sample(sample: Dict[str, Any], *, root: Optional[Path] = None) -> None:
    path = samples_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _play_rating_lock(path):
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(sample) + "\n")


def rewrite_play_rating_samples(
    samples: Sequence[Dict[str, Any]], *, root: Optional[Path] = None
) -> None:
    """Replace play_rating_samples.jsonl atomically under file lock."""
    path = samples_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _play_rating_lock(path):
        text = "".join(json.dumps(row) + "\n" for row in samples)
        path.write_text(text, encoding="utf-8")


def fit_map_knots(samples: List[Dict[str, Any]]) -> List[Dict[str, float]]:
    """Monotone piecewise-linear knots from (Q, calibration_elo_before) samples."""
    if not samples:
        return []
    blocks: List[Dict[str, float]] = []
    for s in sorted(samples, key=lambda row: float(row["q"])):
        blocks.append(
            {
                "sum_w": 1.0,
                "sum_q": float(s["q"]),
                "sum_y": float(s["calibration_elo_before"]),
            }
        )

    i = 0
    while i < len(blocks) - 1:
        avg_i = blocks[i]["sum_y"] / blocks[i]["sum_w"]
        avg_j = blocks[i + 1]["sum_y"] / blocks[i + 1]["sum_w"]
        if avg_i <= avg_j:
            i += 1
            continue
        blocks[i]["sum_w"] += blocks[i + 1]["sum_w"]
        blocks[i]["sum_q"] += blocks[i + 1]["sum_q"]
        blocks[i]["sum_y"] += blocks[i + 1]["sum_y"]
        del blocks[i + 1]
        if i > 0:
            i -= 1

    return [
        {
            "q": round(block["sum_q"] / block["sum_w"], 4),
            "play_rating": round(block["sum_y"] / block["sum_w"], 2),
        }
        for block in blocks
    ]


def interpolate_map(knots: Sequence[Dict[str, float]], q: float) -> Optional[float]:
    if not knots:
        return None
    if q <= knots[0]["q"]:
        return float(knots[0]["play_rating"])
    if q >= knots[-1]["q"]:
        return float(knots[-1]["play_rating"])
    for i in range(len(knots) - 1):
        q0, r0 = knots[i]["q"], knots[i]["play_rating"]
        q1, r1 = knots[i + 1]["q"], knots[i + 1]["play_rating"]
        if q0 <= q <= q1:
            if q1 == q0:
                return float(r0)
            t = (q - q0) / (q1 - q0)
            return float(r0 + t * (r1 - r0))
    return float(knots[-1]["play_rating"])


def fit_play_rating_map(*, root: Optional[Path] = None) -> Dict[str, Any]:
    """Read samples, fit monotone map, write play_rating_map.json under file lock."""
    global _map_cache, _map_cache_path
    out_path = map_path(root)
    sample_rows = load_samples(root)
    payload: Dict[str, Any] = {
        "alpha": Q_ALPHA,
        "beta": Q_BETA,
        "min_samples": MIN_MAP_SAMPLES,
        "sample_count": len(sample_rows),
        "fitted_at": datetime.now(timezone.utc).isoformat(),
        "knots": fit_map_knots(sample_rows) if sample_rows else [],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = continuous_fit_lock_path(root)
    with _play_rating_lock(lock_path):
        _atomic_write_json(out_path, payload)
        _map_cache = payload
        _map_cache_path = str(out_path.resolve())
    return payload


def schedule_map_refit(*, root: Optional[Path] = None, debounce_sec: float = MAP_REFIT_DEBOUNCE_SEC) -> None:
    """No-op: accuracy→Elo map rebuilds only via operator POST (Phase 3)."""
    del root, debounce_sec


def load_play_rating_map(*, root: Optional[Path] = None, force: bool = False) -> Optional[Dict[str, Any]]:
    global _map_cache, _map_cache_path
    path = map_path(root)
    path_key = str(path.resolve()) if path.exists() or path.parent.exists() else str(path)
    if (
        not force
        and _map_cache is not None
        and _map_cache_path == path_key
    ):
        return _map_cache
    data = _read_json_object(path)
    _map_cache = data
    _map_cache_path = path_key
    return data


def _population_stdev(values: Sequence[float]) -> Optional[float]:
    """Population stdev (statistics.pstdev); null when n < 2."""
    if len(values) < 2:
        return None
    return statistics.pstdev(values)


def play_rating_from_q(q: float, *, root: Optional[Path] = None) -> Optional[float]:
    m = load_play_rating_map(root=root)
    if not m or m.get("sample_count", 0) < MIN_MAP_SAMPLES or not m.get("fitted_at"):
        return None
    rating = interpolate_map(m.get("knots", []), q)
    return round(rating, 1) if rating is not None else None


def play_rating_for_side(side: SideQuality, *, root: Optional[Path] = None) -> Optional[float]:
    q = composite_q(side)
    if q is None:
        return None
    return play_rating_from_q(q, root=root)


def play_rating_status_summary(
    *,
    root: Optional[Path] = None,
    engine_elos: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Lightweight operator summary for /calibration: per-engine mean accuracy from
    quality samples (single pass). Does not touch ladder Elo or accuracy→Elo map.
    """
    del engine_elos  # reserved for API compat; not used on the slim status path

    samples = load_samples(root)
    buckets: Dict[str, Dict[str, Any]] = {}
    for sample in samples:
        eid = sample.get("engine_id")
        if not eid:
            continue
        bucket = buckets.setdefault(
            eid,
            {
                "n": 0,
                "acc_sum": 0.0,
                "acc_n": 0,
                "accuracies": [],
            },
        )
        bucket["n"] += 1
        acc = sample.get("accuracy")
        if acc is not None:
            acc_f = float(acc)
            bucket["acc_sum"] += acc_f
            bucket["acc_n"] += 1
            bucket["accuracies"].append(acc_f)

    engines: List[Dict[str, Any]] = []
    for eid, bucket in sorted(buckets.items()):
        mean_accuracy = (
            round(bucket["acc_sum"] / bucket["acc_n"], 1) if bucket["acc_n"] else None
        )
        acc_std = _population_stdev(bucket["accuracies"])
        accuracy_std = round(acc_std, 1) if acc_std is not None else None
        engines.append(
            {
                "engine_id": eid,
                "sample_count": bucket["n"],
                "mean_accuracy": mean_accuracy,
                "accuracy_std": accuracy_std,
            }
        )

    return {
        "sample_count": len(samples),
        "min_samples": MIN_MAP_SAMPLES,
        "engines": engines,
    }


def build_samples_for_calibration_game(
    record: Any,
    white_id: str,
    black_id: str,
    uci_moves: Sequence[str],
    *,
    eval_fn: Any = None,
    ts: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build play-rating sample dicts for eligible floaters; does not write files."""
    if not uci_moves:
        return []

    import sys

    cal_root = project_root() / "elo_calibration"
    if str(cal_root) not in sys.path:
        sys.path.insert(0, str(cal_root))
    from calibration.ratings import is_anchor  # noqa: E402

    from .opponents import get_catalog

    quality = analyse_game(list(uci_moves), eval_fn=eval_fn)
    cat = get_catalog()
    sample_ts = ts or datetime.now(timezone.utc).isoformat()
    samples: List[Dict[str, Any]] = []

    for update in record.updates:
        opp = cat.get(update.opponent_id)
        if not is_sample_eligible(games_played=update.games_played, anchor=is_anchor(opp)):
            continue
        side = quality.white if update.opponent_id == white_id else quality.black
        q = composite_q(side)
        if q is None:
            continue
        sample: Dict[str, Any] = {
            "engine_id": update.opponent_id,
            "game_index": record.game_index,
            "q": round(q, 4),
            "q_midgame": round(side.q_midgame, 4) if side.q_midgame is not None else None,
            "q_trimmed": round(side.q_trimmed, 4) if side.q_trimmed is not None else None,
            "calibration_elo_before": round(update.elo_before, 2),
            "accuracy": round(side.accuracy, 2) if side.accuracy is not None else None,
            "acpl": round(side.acpl, 2) if side.acpl is not None else None,
            "blunder_rate": round(side.blunder_rate, 4) if side.blunder_rate is not None else None,
            "ts": sample_ts,
        }
        samples.append(sample)
    return samples


def rebuild_estimation_samples(
    *,
    root: Optional[Path] = None,
    eval_fn: Any = None,
) -> Dict[str, int]:
    """
    Rewrite play_rating_samples.jsonl from continuous games.jsonl rows with uci_moves.

    Games without stored moves are skipped (no invented samples). Never mutates
    ratings.json / ladder Elo or accuracy→Elo map files.
    """
    import sys

    cal_root = project_root() / "elo_calibration"
    if str(cal_root) not in sys.path:
        sys.path.insert(0, str(cal_root))
    from calibration.ratings import GameRecord  # noqa: E402

    log_path = games_log_path(root)
    all_samples: List[Dict[str, Any]] = []
    games_total = 0
    games_with_moves = 0

    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            games_total += 1
            entry = json.loads(line)
            uci_moves = entry.get("uci_moves") or []
            if not uci_moves:
                continue
            games_with_moves += 1
            record = GameRecord.from_log_dict(entry)
            all_samples.extend(
                build_samples_for_calibration_game(
                    record,
                    entry["white"],
                    entry["black"],
                    uci_moves,
                    eval_fn=eval_fn,
                    ts=entry.get("ts"),
                )
            )

    rewrite_play_rating_samples(all_samples, root=root)
    return {
        "games_total": games_total,
        "games_with_moves": games_with_moves,
        "samples": len(all_samples),
    }


def process_calibration_game_quality(
    record: Any,
    white_id: str,
    black_id: str,
    uci_moves: Sequence[str],
    *,
    eval_fn: Any = None,
    root: Optional[Path] = None,
) -> int:
    """
    Analyse calibration moves and append eligible play-rating samples.
    Returns number of samples appended. Never mutates calibration Elo.
    """
    samples = build_samples_for_calibration_game(
        record,
        white_id,
        black_id,
        uci_moves,
        eval_fn=eval_fn,
    )
    for sample in samples:
        append_play_rating_sample(sample, root=root)
    return len(samples)
