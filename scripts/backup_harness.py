#!/usr/bin/env python3
"""Backup Chess Vision Harness runtime data.

Includes harness registry/results, recent live game dirs, finished-games SQLite,
calibration snapshots and JSONL logs, puzzle/identify stores, and activity audit.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tarfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))
import chess_harness.bootstrap  # noqa: F401

from chess_harness.paths import (
    project_root,
    resolve_base_dir,
    resolve_finished_games_db,
    resolve_models_file,
    resolve_puzzles_dir,
)

HARNESS_FILES = ("models.json", "api_keys.json", "results.jsonl")
HARNESS_RUNTIME_FILES = (
    "puzzle_attempts.json",
    "identify_attempts.json",
    "puzzle_ratings.json",
)
CALIBRATION_ROOT = project_root() / "elo_calibration" / "results"
CALIBRATION_SNAPSHOTS = ("merged_ratings.json", "accuracy_elo_map.json")
CONTINUOUS_FILES = (
    "ratings.json",
    "games.jsonl",
    "play_rating_samples.jsonl",
    "play_rating_map.json",
)


def _archive_suffix() -> str:
    return ".zip" if sys.platform == "win32" else ".tar.gz"


def _select_game_dirs(
    games_dir: Path,
    *,
    max_age_days: int | None,
    max_games: int | None,
) -> list[Path]:
    if not games_dir.is_dir():
        return []
    dirs = [p for p in games_dir.iterdir() if p.is_dir()]
    if max_age_days is not None and max_age_days > 0:
        cutoff = time.time() - max_age_days * 86400
        dirs = [p for p in dirs if p.stat().st_mtime >= cutoff]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if max_games is not None and max_games > 0:
        dirs = dirs[:max_games]
    return dirs


def _calibration_paths() -> list[Path]:
    if not CALIBRATION_ROOT.is_dir():
        return []
    paths: list[Path] = []
    for name in CALIBRATION_SNAPSHOTS:
        candidate = CALIBRATION_ROOT / name
        if candidate.is_file():
            paths.append(candidate)
    continuous = CALIBRATION_ROOT / "continuous"
    if continuous.is_dir():
        for name in CONTINUOUS_FILES:
            candidate = continuous / name
            if candidate.is_file():
                paths.append(candidate)
    for suite_dir in CALIBRATION_ROOT.iterdir():
        if not suite_dir.is_dir() or suite_dir.name == "continuous":
            continue
        for name in ("ratings.json", "games.jsonl"):
            candidate = suite_dir / name
            if candidate.is_file():
                paths.append(candidate)
    return sorted(set(paths))


def _harness_runtime_paths(base_dir: Path) -> list[tuple[Path, Path]]:
    """Return (source, staging-relative) pairs under harness/."""
    pairs: list[tuple[Path, Path]] = []
    for name in HARNESS_RUNTIME_FILES:
        src = base_dir / name
        if src.is_file():
            pairs.append((src, Path("harness") / name))
    audit = base_dir / "audit" / "activity.jsonl"
    if audit.is_file():
        pairs.append((audit, Path("harness") / "audit" / "activity.jsonl"))
    puzzles_dir = resolve_puzzles_dir()
    if puzzles_dir.is_dir() and any(puzzles_dir.iterdir()):
        for src in sorted(puzzles_dir.rglob("*")):
            if src.is_file():
                rel = Path("harness") / "puzzles" / src.relative_to(puzzles_dir)
                pairs.append((src, rel))
    return pairs


def _copy_finished_db(staging: Path) -> dict[str, object]:
    source = resolve_finished_games_db()
    metadata: dict[str, object] = {
        "source": str(source),
        "archived_path": "data/finished_games.sqlite",
        "exists": source.is_file(),
        "size": source.stat().st_size if source.is_file() else 0,
        "rows": 0,
        "integrity_check": None,
    }
    if not source.is_file():
        return metadata

    destination = staging / "data" / "finished_games.sqlite"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(source)) as source_conn, sqlite3.connect(str(destination)) as dest_conn:
        source_conn.backup(dest_conn)
        metadata["integrity_check"] = dest_conn.execute("PRAGMA integrity_check").fetchone()[0]
        metadata["rows"] = dest_conn.execute("SELECT COUNT(*) FROM finished_games").fetchone()[0]
    return metadata


def _stage_backup(
    staging: Path,
    base_dir: Path,
    *,
    max_age_days: int | None,
    max_games: int | None,
) -> dict[str, object]:
    harness_stage = staging / "harness"
    harness_stage.mkdir(parents=True)
    copied: list[str] = []

    for name in HARNESS_FILES:
        src = base_dir / name
        if src.is_file():
            shutil.copy2(src, harness_stage / name)
            copied.append(f"harness/{name}")

    game_dirs = _select_game_dirs(
        base_dir / "games", max_age_days=max_age_days, max_games=max_games
    )
    if game_dirs:
        games_stage = harness_stage / "games"
        games_stage.mkdir()
        for game_dir in game_dirs:
            dest = games_stage / game_dir.name
            shutil.copytree(game_dir, dest)
            copied.append(f"harness/games/{game_dir.name}")

    cal_stage = staging / "calibration"
    cal_stage.mkdir(parents=True, exist_ok=True)
    for src in _calibration_paths():
        rel = src.relative_to(CALIBRATION_ROOT)
        dest = cal_stage / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(f"calibration/{rel.as_posix()}")

    for src, rel in _harness_runtime_paths(base_dir):
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        copied.append(rel.as_posix())

    finished_db = _copy_finished_db(staging)
    if finished_db["exists"]:
        copied.append(str(finished_db["archived_path"]))

    manifest = {
        "created": datetime.now(timezone.utc).isoformat(),
        "harness_dir": str(base_dir),
        "models_file": str(resolve_models_file()),
        "finished_games_db": finished_db,
        "game_dirs": len(game_dirs),
        "paths": copied,
    }
    (staging / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _write_tarball(staging: Path, dest: Path) -> None:
    with tarfile.open(dest, "w:gz") as tar:
        for path in sorted(staging.rglob("*")):
            tar.add(path, arcname=path.relative_to(staging).as_posix())


def _write_zip(staging: Path, dest: Path) -> None:
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(staging).as_posix())


def _prune_old_backups(output_dir: Path, keep: int) -> list[str]:
    if keep <= 0:
        return []
    pattern = f"chess-harness-backup-*{_archive_suffix()}"
    archives = sorted(output_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
    removed: list[str] = []
    while len(archives) > keep:
        old = archives.pop(0)
        old.unlink()
        removed.append(old.name)
    return removed


def run_backup(
    *,
    output_dir: Path,
    max_age_days: int | None,
    max_games: int | None,
    keep: int,
) -> Path:
    base_dir = resolve_base_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    archive = output_dir / f"chess-harness-backup-{stamp}{_archive_suffix()}"

    staging = output_dir / f".staging-{stamp}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    try:
        manifest = _stage_backup(
            staging, base_dir, max_age_days=max_age_days, max_games=max_games
        )
        if sys.platform == "win32":
            _write_zip(staging, archive)
        else:
            _write_tarball(staging, archive)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    removed = _prune_old_backups(output_dir, keep)
    print(json.dumps({"archive": str(archive), "manifest": manifest, "removed": removed}))
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup harness runtime data")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory for archives (default: <harness>/backups)",
    )
    parser.add_argument(
        "--game-days",
        type=int,
        default=30,
        help="Include game dirs modified in last N days (0 = all)",
    )
    parser.add_argument(
        "--max-games",
        type=int,
        default=None,
        help="Cap to the N most recent game dirs (after age filter)",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=7,
        help="Retain this many backup archives in --output (0 = keep all)",
    )
    args = parser.parse_args()

    base_dir = resolve_base_dir()
    output_dir = args.output or (base_dir / "backups")
    max_age = None if args.game_days == 0 else args.game_days

    try:
        run_backup(
            output_dir=output_dir.resolve(),
            max_age_days=max_age,
            max_games=args.max_games,
            keep=args.keep,
        )
    except OSError as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
