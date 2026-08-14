"""Shared path resolution for Chess Vision Harness."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def _repo_root() -> Path:
    """Repository root (parent of ``python/``)."""
    here = Path(__file__).resolve()
    # python/src/chess_harness/paths.py
    candidate = here.parent.parent.parent.parent
    if (candidate / "python").is_dir() and (candidate / "README.md").is_file():
        return candidate
    # Legacy layout: src/chess_harness at repo root
    legacy = here.parent.parent.parent
    if (legacy / "README.md").is_file():
        return legacy
    return candidate


_REPO_ROOT = _repo_root()


def project_root() -> Path:
    return _REPO_ROOT


def resolve_base_dir() -> Path:
    """Resolve harness data directory (games, results, elo).

    Priority: CHESS_HARNESS_DIR env -> <repo>/.chess_harness -> ./.chess_harness
    """
    env = os.getenv("CHESS_HARNESS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    project_data = _REPO_ROOT / ".chess_harness"
    if project_data.exists() or not Path.cwd().joinpath(".chess_harness").exists():
        return project_data
    return Path.cwd() / ".chess_harness"


def resolve_stockfish() -> str:
    """Resolve Stockfish binary path."""
    env = os.getenv("STOCKFISH_PATH")
    if env and Path(env).exists():
        return env

    candidates = [
        _REPO_ROOT / "bin" / "stockfish-windows-x86-64.exe",
        _REPO_ROOT / "bin" / "stockfish",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return "stockfish"


def _resolve_env_path(env_name: str, default: Path) -> Path:
    env = os.getenv(env_name)
    if not env:
        return default
    path = Path(env).expanduser()
    if not path.is_absolute():
        path = project_root() / path
    return path.resolve()


def resolve_opponents_file() -> Path:
    """Resolve path to opponent catalog (version-controlled)."""
    return _resolve_env_path(
        "OPPONENTS_FILE",
        project_root() / "config" / "opponents.json",
    )


def resolve_models_example_file() -> Path:
    return project_root() / "config" / "models.json.example"


def resolve_models_file() -> Path:
    """Resolve path to inscribed models registry (runtime under .chess_harness/)."""
    return _resolve_env_path(
        "MODELS_FILE",
        resolve_base_dir() / "models.json",
    )


def resolve_followup_approvals_file() -> Path:
    """Runtime store for follow-up approval lifecycle (under CHESS_HARNESS_DIR).

    Kept outside game state files and the finished-games SQLite.
    """
    return resolve_base_dir() / "followup_approvals.json"


def resolve_child_credentials_file() -> Path:
    """Runtime store for side-scoped child credentials (under CHESS_HARNESS_DIR)."""
    return resolve_base_dir() / "child_credentials.json"


def resolve_orchestrations_file() -> Path:
    """Runtime store for parent orchestration records (under CHESS_HARNESS_DIR)."""
    return resolve_base_dir() / "orchestrations.json"


def resolve_puzzles_dir() -> Path:
    """Runtime puzzle dataset directory (under CHESS_HARNESS_DIR, outside git).

    Puzzle rows are imported data (Lichess CC0) and are never committed to the
    repository; only the content manifest is committed.
    """
    return _resolve_env_path(
        "CHESS_HARNESS_PUZZLES_DIR",
        resolve_base_dir() / "puzzles",
    )


def resolve_puzzle_dataset_file() -> Path:
    """Indexed puzzle dataset (id -> record), runtime, never committed."""
    return resolve_puzzles_dir() / "puzzles.json"


def resolve_puzzle_manifest_file() -> Path:
    """Runtime import manifest (version, source, license, counts)."""
    return resolve_puzzles_dir() / "manifest.json"


def resolve_puzzle_attempts_file() -> Path:
    """Runtime store for puzzle attempts (under CHESS_HARNESS_DIR).

    Puzzle attempts are not games and never appear in ``results.jsonl``.
    """
    return resolve_base_dir() / "puzzle_attempts.json"


def resolve_puzzle_ratings_file() -> Path:
    """Runtime store for Glicko-2 puzzle ratings (under CHESS_HARNESS_DIR).

    Holds per-agent puzzle ratings and runtime puzzle difficulty. Independent
    of ``models.json`` — ``inscribe`` / ``reset_all_elo`` never touch it.
    """
    return resolve_base_dir() / "puzzle_ratings.json"


def resolve_identify_attempts_file() -> Path:
    """Runtime store for board-identification attempts (under CHESS_HARNESS_DIR).

    Identification attempts are not games and never appear in ``results.jsonl``.
    """
    return resolve_base_dir() / "identify_attempts.json"


def resolve_puzzles_content_manifest() -> Path:
    """Committed content manifest describing the dataset source and license."""
    return project_root() / "config" / "puzzles_manifest.json"


def resolve_finished_games_db() -> Path:
    """Permanent finished-games SQLite path (outside ``.chess_harness/``).

    Default: ``<repo>/data/finished_games.sqlite``. Override with
    ``CHESS_HARNESS_FINISHED_DB`` for local experiments only.
    """
    return _resolve_env_path(
        "CHESS_HARNESS_FINISHED_DB",
        project_root() / "data" / "finished_games.sqlite",
    )


def resolve_calibration_worker_dir() -> Path:
    """Runtime dir for calibration worker IPC (status file, pid marker)."""
    return resolve_base_dir() / "calibration_worker"


def default_calibration_worker_port() -> int:
    raw = os.getenv("CHESS_HARNESS_CALIBRATION_WORKER_PORT", "8766")
    try:
        return max(1024, min(65535, int(raw)))
    except ValueError:
        return 8766


def resolve_publish_snapshots_dir() -> Path:
    """Runtime leaderboard snapshot dir (never committed).

    ``chess-harness serve`` writes debounced snapshots here after rated finishes
    and calibration ticks. Intentional Sleeping publish uses
    ``chess-harness snapshot-leaderboard`` → ``public-site/data/*.json``.
    """
    return _resolve_env_path(
        "CHESS_HARNESS_PUBLISH_DIR",
        resolve_base_dir() / "publish",
    )


def ensure_models_file() -> Path:
    """Create runtime models.json from config example if missing."""
    path = resolve_models_file()
    if path.is_file():
        return path
    example = resolve_models_example_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    if example.is_file():
        shutil.copyfile(example, path)
    else:
        path.write_text('{"version":1,"models":[]}\n', encoding="utf-8")
    return path


def configure_environment() -> None:
    """Set default environment variables if not already configured."""
    if not os.getenv("STOCKFISH_PATH"):
        sf = resolve_stockfish()
        if sf != "stockfish" or Path(sf).exists():
            os.environ["STOCKFISH_PATH"] = sf
    ensure_models_file()
