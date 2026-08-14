"""Phase 9b: serve writes runtime publish dir; CLI writes git Sleeping fallbacks."""

from __future__ import annotations

from pathlib import Path

import pytest

from chess_harness.snapshot_leaderboard import (
    export_git_publish_snapshots,
    export_public_snapshots,
    git_publish_leaderboard_path,
)


@pytest.fixture
def harness_dir(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    harness.mkdir()
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))
    return harness


def test_export_public_snapshots_uses_runtime_publish_dir(harness_dir, monkeypatch):
    publish = harness_dir / "publish"
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.resolve_publish_snapshots_dir",
        lambda: publish,
    )
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.default_output_path",
        lambda: publish / "leaderboard.json",
    )
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.default_puzzle_leaderboard_path",
        lambda: publish / "puzzles_leaderboard.json",
    )
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.default_identify_leaderboard_path",
        lambda: publish / "identify_leaderboard.json",
    )
    written = export_public_snapshots()
    ladder = written["leaderboard"]
    assert ladder == publish / "leaderboard.json"
    assert ladder.is_file()
    assert "public-site" not in str(ladder).replace("\\", "/")


def test_export_git_publish_snapshots_writes_public_site_data(harness_dir, tmp_path, monkeypatch):
    repo_data = tmp_path / "public-site" / "data"
    repo_data.mkdir(parents=True)
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.project_root",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard._inject_inline_snapshot",
        lambda _json: None,
    )
    written = export_git_publish_snapshots()
    assert written["leaderboard"] == repo_data / "leaderboard.json"
    assert written["puzzles"] == repo_data / "puzzles_leaderboard.json"
    assert written["identify"] == repo_data / "identify_leaderboard.json"
    for path in written.values():
        assert path.is_file()


def test_git_publish_leaderboard_path_points_to_public_site(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.project_root",
        lambda: tmp_path,
    )
    assert git_publish_leaderboard_path() == tmp_path / "public-site" / "data" / "leaderboard.json"
