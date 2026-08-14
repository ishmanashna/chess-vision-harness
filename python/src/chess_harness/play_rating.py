"""
Play-rating samples: monotone accuracy → display strength (not ladder Elo).

Training samples come from continuous calibration floaters only. The
accuracy→Elo map itself lives in accuracy_elo_map.py and changes only via the
operator's rebuild endpoint. Never calls CalibrationLadder.record_game or
writes ratings.json.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

import filelock

from .game_quality import SideQuality, analyse_game, composite_q_value
from .paths import project_root

CONTINUOUS_SUITE = "continuous"
MIN_MAP_SAMPLES = 30
MIN_GAMES_FOR_SAMPLE = 101


def continuous_results_dir(root: Optional[Path] = None) -> Path:
    base = root if root is not None else project_root() / "elo_calibration" / "results"
    return base / CONTINUOUS_SUITE


def samples_path(root: Optional[Path] = None) -> Path:
    return continuous_results_dir(root) / "play_rating_samples.jsonl"


def games_log_path(root: Optional[Path] = None) -> Path:
    return continuous_results_dir(root) / "games.jsonl"


def continuous_fit_lock_path(root: Optional[Path] = None) -> Path:
    """Shared lock for map-file refits (estimation bake-off CLI/tests)."""
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
    """Whether a side may contribute a quality sample for the accuracy→Elo map.

    Floaters need cumulative games_played >= 101 (ladder total after record_game).
    Anchors are eligible from the first scored calibration game — their Elo is the
    fixed catalog reference and should stretch the accuracy→Elo table at the top.
    """
    if anchor:
        return games_played >= 1
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
    import sys

    cal_root = project_root() / "elo_calibration"
    if str(cal_root) not in sys.path:
        sys.path.insert(0, str(cal_root))
    from calibration.jsonl_store import append_jsonl_line  # noqa: E402

    path = samples_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _play_rating_lock(path):
        append_jsonl_line(path, sample)


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
    """Monotone piecewise-linear knots from (x, reference Elo) samples.

    x is composite Q for the estimation bake-off, or mean accuracy for the
    accuracy→Elo display map (see accuracy_elo_map.py).
    """
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


def _population_stdev(values: Sequence[float]) -> Optional[float]:
    """Population stdev (statistics.pstdev); null when n < 2."""
    if len(values) < 2:
        return None
    return statistics.pstdev(values)


def play_rating_for_side(side: SideQuality, *, root: Optional[Path] = None) -> Optional[float]:
    if side is None or side.accuracy is None:
        return None
    from .accuracy_elo_map import play_rating_from_accuracy

    return play_rating_from_accuracy(side.accuracy, root=root)


def play_rating_status_summary(
    *,
    root: Optional[Path] = None,
    engine_elos: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Lightweight operator summary for /calibration: per-engine mean accuracy and
    per-sample play rating via the accuracy→Elo map (single pass). Does not
    touch ladder Elo or map files.
    """
    del engine_elos  # reserved for API compat; not used on the slim status path

    from .accuracy_elo_map import play_rating_from_accuracy

    samples = load_samples(root)
    buckets: Dict[str, List[float]] = {}
    for sample in samples:
        eid = sample.get("engine_id")
        acc = sample.get("accuracy")
        if not eid or acc is None:
            continue
        buckets.setdefault(str(eid), []).append(float(acc))

    engines: List[Dict[str, Any]] = []
    for eid, accs in sorted(buckets.items()):
        ratings = [
            rating
            for acc in accs
            if (rating := play_rating_from_accuracy(acc, root=root)) is not None
        ]
        acc_std = _population_stdev(accs)
        engines.append(
            {
                "engine_id": eid,
                "sample_count": len(accs),
                "mean_accuracy": round(sum(accs) / len(accs), 1),
                "mean_play_rating": (
                    round(sum(ratings) / len(ratings), 1) if ratings else None
                ),
                "accuracy_std": round(acc_std, 1) if acc_std is not None else None,
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
    """Build play-rating sample dicts for eligible floaters and anchors; does not write files."""
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
    sampled_ids: set[str] = set()

    def _append_sample(
        engine_id: str,
        side: Any,
        *,
        elo_before: float,
        games_played: int,
        anchor: bool,
    ) -> None:
        if engine_id in sampled_ids:
            return
        if not is_sample_eligible(games_played=games_played, anchor=anchor):
            return
        q = composite_q(side)
        if q is None:
            return
        samples.append(
            {
                "engine_id": engine_id,
                "game_index": record.game_index,
                "q": round(q, 4),
                "q_midgame": round(side.q_midgame, 4) if side.q_midgame is not None else None,
                "q_trimmed": round(side.q_trimmed, 4) if side.q_trimmed is not None else None,
                "calibration_elo_before": round(float(elo_before), 2),
                "accuracy": round(side.accuracy, 2) if side.accuracy is not None else None,
                "acpl": round(side.acpl, 2) if side.acpl is not None else None,
                "blunder_rate": round(side.blunder_rate, 4)
                if side.blunder_rate is not None
                else None,
                "ts": sample_ts,
            }
        )
        sampled_ids.add(engine_id)

    for update in record.updates:
        opp = cat.get(update.opponent_id)
        side = quality.white if update.opponent_id == white_id else quality.black
        _append_sample(
            update.opponent_id,
            side,
            elo_before=update.elo_before,
            games_played=update.games_played,
            anchor=is_anchor(opp) if opp else False,
        )

    # Anchors never appear in rating updates — still sample them from game sides.
    for engine_id, side, elo_before in (
        (white_id, quality.white, record.white_elo_before),
        (black_id, quality.black, record.black_elo_before),
    ):
        opp = cat.get(engine_id)
        if not opp or not is_anchor(opp):
            continue
        _append_sample(
            engine_id,
            side,
            elo_before=elo_before,
            games_played=1,
            anchor=True,
        )

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
