"""
Play-rating map: monotone Q → display strength (not ladder Elo).

Training samples come from continuous calibration floaters only.
Never calls CalibrationLadder.record_game or writes ratings.json.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

import filelock

from .game_quality import SideQuality, analyse_game
from .paths import project_root

CONTINUOUS_SUITE = "continuous"
Q_ALPHA = 8.0
Q_BETA = 25.0
MIN_MAP_SAMPLES = 30
MIN_GAMES_FOR_SAMPLE = 101
MAP_REFIT_DEBOUNCE_SEC = 1.0

_map_cache: Optional[Dict[str, Any]] = None
_refit_timer: Optional[threading.Timer] = None
_refit_timer_lock = threading.Lock()


def continuous_results_dir(root: Optional[Path] = None) -> Path:
    base = root if root is not None else project_root() / "elo_calibration" / "results"
    return base / CONTINUOUS_SUITE


def samples_path(root: Optional[Path] = None) -> Path:
    return continuous_results_dir(root) / "play_rating_samples.jsonl"


def map_path(root: Optional[Path] = None) -> Path:
    return continuous_results_dir(root) / "play_rating_map.json"


@contextmanager
def _play_rating_lock(path: Path) -> Iterator[None]:
    lock = filelock.FileLock(str(path.with_suffix(path.suffix + ".lock")), timeout=30)
    lock.acquire()
    try:
        yield
    finally:
        if lock.is_locked:
            lock.release()


def composite_q(side: SideQuality) -> Optional[float]:
    """Q = accuracy − α·normalized_acpl − β·blunder_rate."""
    if side.accuracy is None or side.normalized_acpl is None or side.blunder_rate is None:
        return None
    return side.accuracy - Q_ALPHA * side.normalized_acpl - Q_BETA * side.blunder_rate


def is_sample_eligible(*, games_played: int, anchor: bool) -> bool:
    """Floaters with games_played >= 101 after record_game; anchors never."""
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
    global _map_cache
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
    with _play_rating_lock(out_path):
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if root is None:
        _map_cache = payload
    return payload


def schedule_map_refit(*, root: Optional[Path] = None, debounce_sec: float = MAP_REFIT_DEBOUNCE_SEC) -> None:
    """Debounced background refit (thread-safe)."""
    global _refit_timer

    def _run() -> None:
        fit_play_rating_map(root=root)

    with _refit_timer_lock:
        if _refit_timer is not None:
            _refit_timer.cancel()
        _refit_timer = threading.Timer(debounce_sec, _run)
        _refit_timer.daemon = True
        _refit_timer.start()


def load_play_rating_map(*, root: Optional[Path] = None, force: bool = False) -> Optional[Dict[str, Any]]:
    global _map_cache
    if _map_cache is not None and not force and root is None:
        return _map_cache
    path = map_path(root)
    if not path.exists():
        if root is None:
            _map_cache = None
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if root is None:
        _map_cache = data
    return data


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
    if not uci_moves:
        return 0

    import sys

    cal_root = project_root() / "elo_calibration"
    if str(cal_root) not in sys.path:
        sys.path.insert(0, str(cal_root))
    from calibration.ratings import is_anchor  # noqa: E402

    from .opponents import get_catalog

    quality = analyse_game(list(uci_moves), eval_fn=eval_fn)
    cat = get_catalog()
    appended = 0
    ts = datetime.now(timezone.utc).isoformat()

    for update in record.updates:
        opp = cat.get(update.opponent_id)
        if not is_sample_eligible(games_played=update.games_played, anchor=is_anchor(opp)):
            continue
        side = quality.white if update.opponent_id == white_id else quality.black
        q = composite_q(side)
        if q is None:
            continue
        append_play_rating_sample(
            {
                "engine_id": update.opponent_id,
                "game_index": record.game_index,
                "q": round(q, 4),
                "calibration_elo_before": round(update.elo_before, 2),
                "accuracy": round(side.accuracy, 2) if side.accuracy is not None else None,
                "acpl": round(side.acpl, 2) if side.acpl is not None else None,
                "blunder_rate": round(side.blunder_rate, 4) if side.blunder_rate is not None else None,
                "ts": ts,
            },
            root=root,
        )
        appended += 1

    if appended:
        schedule_map_refit(root=root)
    return appended
