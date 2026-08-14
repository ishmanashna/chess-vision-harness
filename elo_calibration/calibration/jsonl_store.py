"""Bounded append-only JSONL for calibration game and sample logs."""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_MAX_LINES = int(os.environ.get("CHESS_HARNESS_MAX_CALIBRATION_JSONL_LINES", "100000"))
_TRIM_CHECK_MIN_BYTES = 5 * 1024 * 1024


def append_jsonl_line(
    path: Path,
    payload: dict,
    *,
    max_lines: int | None = None,
) -> None:
    """Append one JSON object as a line; trim to the newest ``max_lines`` when large."""
    limit = DEFAULT_MAX_LINES if max_lines is None else max_lines
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
    if limit > 0:
        trim_jsonl_tail(path, limit)


def trim_jsonl_tail(path: Path, max_lines: int) -> None:
    """Keep only the newest ``max_lines`` rows when the file is large enough to check."""
    if max_lines <= 0 or not path.is_file():
        return
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size < _TRIM_CHECK_MIN_BYTES:
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) <= max_lines:
        return
    path.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")
