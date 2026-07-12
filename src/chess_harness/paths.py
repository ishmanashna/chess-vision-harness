"""Shared path resolution for Chess Vision Harness."""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def project_root() -> Path:
    return _PROJECT_ROOT


def resolve_base_dir() -> Path:
    """Resolve harness data directory (games, results, elo).

    Priority: CHESS_HARNESS_DIR env -> <project>/.chess_harness -> ./.chess_harness
    """
    env = os.getenv("CHESS_HARNESS_DIR")
    if env:
        return Path(env).expanduser().resolve()
    project_data = _PROJECT_ROOT / ".chess_harness"
    if project_data.exists() or not Path.cwd().joinpath(".chess_harness").exists():
        return project_data
    return Path.cwd() / ".chess_harness"


def resolve_stockfish() -> str:
    """Resolve Stockfish binary path."""
    env = os.getenv("STOCKFISH_PATH")
    if env and Path(env).exists():
        return env

    candidates = [
        _PROJECT_ROOT / "bin" / "stockfish-windows-x86-64.exe",
        _PROJECT_ROOT / "bin" / "stockfish",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return "stockfish"


def resolve_opponents_file() -> Path:
    """Resolve path to opponent catalog (version-controlled)."""
    env = os.getenv("OPPONENTS_FILE")
    if env:
        return Path(env).expanduser().resolve()
    return project_root() / "opponents.json"


def resolve_models_file() -> Path:
    """Resolve path to inscribed models registry (version-controlled)."""
    env = os.getenv("MODELS_FILE")
    if env:
        return Path(env).expanduser().resolve()
    return project_root() / "models.json"


def configure_environment() -> None:
    """Set default environment variables if not already configured."""
    if not os.getenv("STOCKFISH_PATH"):
        sf = resolve_stockfish()
        if sf != "stockfish" or Path(sf).exists():
            os.environ["STOCKFISH_PATH"] = sf
