"""Backup script creates an archive from a temp harness dir."""

from __future__ import annotations

import json
import sqlite3
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from backup_harness import run_backup  # noqa: E402


def _read_manifest(archive: Path) -> dict:
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            return json.loads(zf.read("manifest.json"))
    with tarfile.open(archive, "r:gz") as tar:
        return json.loads(tar.extractfile("manifest.json").read())


def _archive_names(archive: Path) -> set[str]:
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            return set(zf.namelist())
    with tarfile.open(archive, "r:gz") as tar:
        return {m.name for m in tar.getmembers() if m.isfile()}


def test_backup_creates_archive(tmp_path, monkeypatch):
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "models.json").write_text('{"version":1,"models":[]}\n', encoding="utf-8")
    (harness / "api_keys.json").write_text('{"keys":[]}\n', encoding="utf-8")
    (harness / "results.jsonl").write_text('{"game_id":"g1"}\n', encoding="utf-8")
    finished_db = tmp_path / "finished_games.sqlite"
    monkeypatch.setenv("CHESS_HARNESS_FINISHED_DB", str(finished_db))
    with sqlite3.connect(finished_db) as conn:
        conn.execute("CREATE TABLE finished_games (game_id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO finished_games VALUES ('old-finished-game')")
        conn.commit()
    games = harness / "games" / "game-test-1"
    games.mkdir(parents=True)
    (games / "state.json").write_text('{"game_id":"game-test-1"}\n', encoding="utf-8")

    audit = harness / "audit"
    audit.mkdir(parents=True)
    (audit / "activity.jsonl").write_text('{"action":"create"}\n', encoding="utf-8")
    puzzles = harness / "puzzles"
    puzzles.mkdir()
    (puzzles / "manifest.json").write_text('{"version":1}\n', encoding="utf-8")
    (harness / "puzzle_attempts.json").write_text("{}\n", encoding="utf-8")
    cal_root = tmp_path / "elo_calibration" / "results"
    continuous = cal_root / "continuous"
    continuous.mkdir(parents=True)
    (continuous / "games.jsonl").write_text('{"game_index":1}\n', encoding="utf-8")
    (continuous / "play_rating_samples.jsonl").write_text('{"engine_id":"e1"}\n', encoding="utf-8")
    (cal_root / "accuracy_elo_map.json").write_text('{}\n', encoding="utf-8")
    monkeypatch.setattr("backup_harness.CALIBRATION_ROOT", cal_root)

    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))
    archive = run_backup(
        output_dir=tmp_path / "backups",
        max_age_days=None,
        max_games=None,
        keep=3,
    )

    assert archive.is_file()
    names = _archive_names(archive)
    assert "manifest.json" in names
    assert "harness/models.json" in names
    assert "harness/games/game-test-1/state.json" in names
    assert "data/finished_games.sqlite" in names
    assert "harness/audit/activity.jsonl" in names
    assert "harness/puzzles/manifest.json" in names
    assert "harness/puzzle_attempts.json" in names
    assert "calibration/continuous/games.jsonl" in names
    assert "calibration/continuous/play_rating_samples.jsonl" in names
    assert "calibration/accuracy_elo_map.json" in names
    manifest = _read_manifest(archive)
    assert manifest["game_dirs"] == 1
    assert manifest["finished_games_db"]["rows"] == 1
    assert manifest["finished_games_db"]["integrity_check"] == "ok"
    restored_db = tmp_path / "restored.sqlite"
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            restored_db.write_bytes(zf.read("data/finished_games.sqlite"))
    else:
        with tarfile.open(archive, "r:gz") as tar:
            restored_db.write_bytes(tar.extractfile("data/finished_games.sqlite").read())
    with sqlite3.connect(restored_db) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT game_id FROM finished_games").fetchone()[0] == "old-finished-game"
