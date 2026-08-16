"""Tests for bounded calibration JSONL append."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "elo_calibration"))

from calibration.jsonl_store import (  # noqa: E402
    append_jsonl_line,
    repair_jsonl_corrupt_tail,
    trim_jsonl_tail,
)


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


def test_repair_jsonl_corrupt_tail_drops_trailing_garbage(tmp_path):
    path = tmp_path / "games.jsonl"
    path.write_text(
        '{"game_index": 1, "white": "a", "black": "b"}\n'
        "partial write\n"
        "{not json\n",
        encoding="utf-8",
    )

    removed = repair_jsonl_corrupt_tail(path)

    assert removed == 2
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["game_index"] == 1


def test_append_jsonl_line_repairs_corrupt_tail_on_write(tmp_path):
    path = tmp_path / "games.jsonl"
    path.write_text('{"game_index": 1}\ncorrupt tail\n', encoding="utf-8")

    append_jsonl_line(path, {"game_index": 2})

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["game_index"] for row in rows] == [1, 2]

