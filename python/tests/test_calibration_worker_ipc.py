"""Worker status snapshot read path (Phase 2)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.calibration_worker_ipc import (  # noqa: E402
    default_idle_worker_snapshot,
    read_worker_status_snapshot,
)


def test_read_worker_status_snapshot_missing_file(monkeypatch, tmp_path):
    worker_dir = tmp_path / "calibration_worker"
    worker_dir.mkdir()
    monkeypatch.setattr(
        "chess_harness.calibration_worker_ipc.resolve_calibration_worker_dir",
        lambda: worker_dir,
    )
    snap = read_worker_status_snapshot()
    assert snap["active"] is False
    assert snap["continuous_engines"] == []
    assert snap["pairing_mode"] == "floaters"
    assert snap["calibratable_engines"]


def test_read_worker_status_snapshot_from_disk(monkeypatch, tmp_path):
    worker_dir = tmp_path / "calibration_worker"
    worker_dir.mkdir()
    status_path = worker_dir / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "active": True,
                "continuous_engines": ["engine-a"],
                "in_flight_by_engine": {"engine-a": 1},
                "recent_games": [{"game_index": 1}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "chess_harness.calibration_worker_ipc.resolve_calibration_worker_dir",
        lambda: worker_dir,
    )
    snap = read_worker_status_snapshot()
    assert snap["active"] is True
    assert snap["continuous_engines"] == ["engine-a"]
    assert snap["in_flight_by_engine"]["engine-a"] == 1
    assert snap["recent_games"][0]["game_index"] == 1
    assert snap["pairing_mode"] == default_idle_worker_snapshot()["pairing_mode"]
