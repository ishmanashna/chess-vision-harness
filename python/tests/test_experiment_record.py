"""Offline run metadata, isolation, and terminal-state checks."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "experiments" / "template"


@pytest.fixture
def recorder(monkeypatch):
    spec = importlib.util.spec_from_file_location("experiment_record", ROOT / "experiments/run_record.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "code_identity", lambda: ("test-revision", False))
    return module.RunRecord


@pytest.fixture
def config():
    return json.loads((TEMPLATE / "config.json").read_text(encoding="utf-8"))


def test_progress_identifiers_hashes_and_unavailable_usage(recorder, config, tmp_path):
    run = recorder(tmp_path, "run-1", config, b"fixture prompt")
    run.event("heartbeat", seat_id="seat-1", game_id="game-fixture", phase="observe",
              retry_count=0, rate_limited=False)
    manifest = json.loads((run.directory / "manifest.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (run.directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert manifest["prompt_sha256"] == hashlib.sha256(b"fixture prompt").hexdigest()
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
    assert manifest["config_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert manifest["usage"] == {"tokens": None, "cost_usd": None, "source": "unavailable"}
    assert manifest["last_progress_at"] == events[-1]["ts"]
    assert manifest["code_revision"] == "test-revision"
    assert events[-1]["run_id"] == "run-1"
    assert events[-1]["game_id"] == "game-fixture"
    assert events[-1]["retry_count"] == 0
    assert events[-1]["rate_limited"] is False


@pytest.mark.parametrize("status", ["completed", "failed", "abandoned"])
def test_terminal_runs_have_report_and_reject_later_events(recorder, config, tmp_path, status):
    run = recorder(tmp_path, "terminal", config, b"prompt")
    run.finish(status, reason="explicit reason", summary="Operational summary only.")
    assert run.manifest["status"] == status
    assert run.manifest["ended_at"] is not None
    assert f"Status: {status}" in (run.directory / "report.md").read_text(encoding="utf-8")
    before = (run.directory / "events.jsonl").read_bytes()
    with pytest.raises(ValueError, match="terminal run"):
        run.event("heartbeat")
    with pytest.raises(ValueError, match="terminal run"):
        run.finish(status, reason="again", summary="again")
    assert (run.directory / "events.jsonl").read_bytes() == before


def test_existing_id_cannot_overwrite_evidence(recorder, config, tmp_path):
    run = recorder(tmp_path, "unique", config, b"original")
    before = (run.directory / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        recorder(tmp_path, "unique", config, b"different")
    assert (run.directory / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("run_id", ["../escape", "nested/run", "..", "C:\\outside", ""])
def test_invalid_ids_never_create_directories(recorder, config, tmp_path, run_id):
    output = tmp_path / "runs"
    with pytest.raises(ValueError, match="simple names"):
        recorder(output, run_id, config, b"prompt")
    assert not output.exists()


def test_explicit_synthetic_flag_required(recorder, config, tmp_path):
    del config["synthetic"]
    output = tmp_path / "runs"
    with pytest.raises(ValueError, match="synthetic"):
        recorder(output, "invalid", config, b"prompt")
    assert not output.exists()


def test_offline_example_writes_three_matching_artifacts(tmp_path):
    cmd = [sys.executable, str(TEMPLATE / "run.py"), "--run-id", "smoke", "--output-root", str(tmp_path)]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    directory = tmp_path / "smoke"
    assert {p.name for p in directory.iterdir()} == {"manifest.json", "events.jsonl", "report.md"}
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    events = [json.loads(line) for line in (directory / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert manifest["status"] == "completed" and manifest["synthetic"] is True
    assert len(events) == 5
    assert all(event["run_id"] == manifest["run_id"] for event in events)
    assert all("game_id" not in event for event in events)
    assert "No provider calls" in (directory / "report.md").read_text(encoding="utf-8")
    before = (directory / "manifest.json").read_bytes()
    duplicate = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert duplicate.returncode != 0
    assert (directory / "manifest.json").read_bytes() == before
