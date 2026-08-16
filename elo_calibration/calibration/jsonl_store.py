"""Bounded append-only JSONL for calibration game and sample logs."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import filelock

DEFAULT_MAX_LINES = int(os.environ.get("CHESS_HARNESS_MAX_CALIBRATION_JSONL_LINES", "100000"))
_TRIM_CHECK_MIN_BYTES = 5 * 1024 * 1024


@contextmanager
def _jsonl_lock(path: Path) -> Iterator[None]:
    lock = filelock.FileLock(str(path.with_suffix(path.suffix + ".lock")), timeout=30)
    lock.acquire()
    try:
        yield
    finally:
        if lock.is_locked:
            lock.release()


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text via temp + replace; Windows-safe retries if the target is briefly locked."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    last_err: BaseException | None = None
    for attempt in range(12):
        try:
            os.replace(str(tmp), str(path))
            return
        except (PermissionError, OSError) as exc:
            last_err = exc
            time.sleep(0.05 * (attempt + 1))
    path.write_text(text, encoding="utf-8")
    tmp.unlink(missing_ok=True)
    if last_err is not None:
        raise last_err


def append_jsonl_line(
    path: Path,
    payload: dict,
    *,
    max_lines: int | None = None,
) -> None:
    """Append one JSON object as a line; trim to the newest ``max_lines`` when large."""
    limit = DEFAULT_MAX_LINES if max_lines is None else max_lines
    with _jsonl_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        repair_jsonl_corrupt_tail(path, _locked=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
        if limit > 0:
            trim_jsonl_tail(path, limit, _locked=True)


def trim_jsonl_tail(path: Path, max_lines: int, *, _locked: bool = False) -> None:
    """Keep only the newest ``max_lines`` rows when the file is large enough to check."""
    if not _locked:
        with _jsonl_lock(path):
            trim_jsonl_tail(path, max_lines, _locked=True)
        return
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
    _atomic_write_text(path, "\n".join(lines[-max_lines:]) + "\n")


def repair_jsonl_corrupt_tail(path: Path, *, _locked: bool = False) -> int:
    """Drop trailing non-JSON lines (partial writes). Returns lines removed."""
    if not _locked:
        with _jsonl_lock(path):
            return repair_jsonl_corrupt_tail(path, _locked=True)
    if not path.is_file():
        return 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    if not lines:
        return 0
    kept = list(lines)
    removed = 0
    while kept:
        stripped = kept[-1].strip()
        if not stripped:
            kept.pop()
            removed += 1
            continue
        try:
            json.loads(stripped)
            break
        except json.JSONDecodeError:
            kept.pop()
            removed += 1
    if removed:
        _atomic_write_text(path, ("\n".join(kept) + "\n") if kept else "")
    return removed
