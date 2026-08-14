"""Tests for bounded calibration JSONL append."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "elo_calibration"))

from calibration.jsonl_store import append_jsonl_line, trim_jsonl_tail  # noqa: E402


def test_trim_jsonl_tail_keeps_newest_lines(tmp_path, monkeypatch):
    monkeypatch.setattr("calibration.jsonl_store._TRIM_CHECK_MIN_BYTES", 0)
    path = tmp_path / "games.jsonl"
    path.write_text(
        "".join(json.dumps({"i": i}) + "\n" for i in range(5)),
        encoding="utf-8",
    )

    trim_jsonl_tail(path, 2)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["i"] for row in rows] == [3, 4]


def test_append_jsonl_line_trims_when_over_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("calibration.jsonl_store._TRIM_CHECK_MIN_BYTES", 0)
    path = tmp_path / "samples.jsonl"
    for i in range(5):
        append_jsonl_line(path, {"i": i}, max_lines=3)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["i"] for row in rows] == [2, 3, 4]
