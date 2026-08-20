"""Runtime paths for the internal runner."""

from __future__ import annotations

import os
from pathlib import Path

from ..paths import project_root, resolve_base_dir


def runner_dir(base_dir: Path | None = None) -> Path:
    root = base_dir or resolve_base_dir()
    return root / "runner"


def default_config_path() -> Path:
    env = os.getenv("CHESS_HARNESS_RUNNER_CONFIG")
    if env:
        path = Path(env).expanduser()
        if not path.is_absolute():
            path = project_root() / path
        return path.resolve()
    local = resolve_base_dir() / "runner" / "slots.json"
    if local.is_file():
        return local
    return project_root() / "config" / "runner_slots.json.example"


def example_config_path() -> Path:
    return project_root() / "config" / "runner_slots.json.example"


def keys_path(base_dir: Path | None = None) -> Path:
    return runner_dir(base_dir) / "keys.json"


def probe_status_path(base_dir: Path | None = None) -> Path:
    return runner_dir(base_dir) / "probe_status.json"


def log_path(base_dir: Path | None = None) -> Path:
    return runner_dir(base_dir) / "runner.jsonl"
