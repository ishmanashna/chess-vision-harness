"""Backup script creates an archive from a temp harness dir."""

from __future__ import annotations

import json
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
    games = harness / "games" / "game-test-1"
    games.mkdir(parents=True)
    (games / "state.json").write_text('{"game_id":"game-test-1"}\n', encoding="utf-8")

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
    assert _read_manifest(archive)["game_dirs"] == 1
