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


def resolve_finished_games_db() -> Path:
    """Permanent finished-games SQLite path (outside ``.chess_harness/``).

    Default: ``<repo>/data/finished_games.sqlite``. Override with
    ``CHESS_HARNESS_FINISHED_DB`` for local experiments only.
    """
    return _resolve_env_path(
        "CHESS_HARNESS_FINISHED_DB",
        project_root() / "data" / "finished_games.sqlite",
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
