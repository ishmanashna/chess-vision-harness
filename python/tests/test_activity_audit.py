"""Tests for light activity audit (no auth)."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.activity_audit import (
    activity_log_path,
    hash_client_ip,
    record_activity,
    tail_activity,
)


def test_hash_client_ip_stable_with_salt(monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_AUDIT_SALT", "test-salt")
    a = hash_client_ip("1.2.3.4")
    b = hash_client_ip("1.2.3.4")
    c = hash_client_ip("5.6.7.8")
    assert a == b
    assert a != c
    assert len(a) == 16


def test_record_and_tail_activity(tmp_path, monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_AUDIT_SALT", "salt")
    harness = tmp_path / "harness"
    harness.mkdir()
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))

    record_activity(
        "inscribe",
        model_id="agent-a",
        client_ip="10.0.0.1",
        user_agent="TestAgent/1.0",
        base_dir=harness,
    )
    record_activity(
        "create_game",
        model_id="agent-a",
        game_id="game-1",
        client_ip="10.0.0.1",
        user_agent="TestAgent/1.0",
        base_dir=harness,
    )

    path = activity_log_path(harness)
    assert path.exists()
    rows = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 2
    first = json.loads(rows[0])
    assert first["action"] == "inscribe"
    assert first["model_id"] == "agent-a"
    assert "ip_hash" in first
    assert "10.0.0.1" not in path.read_text(encoding="utf-8")

    tail = tail_activity(1, base_dir=harness)
    assert len(tail) == 1
    assert tail[0]["action"] == "create_game"
    assert tail[0]["game_id"] == "game-1"
