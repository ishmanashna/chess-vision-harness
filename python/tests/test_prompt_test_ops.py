"""Tests for Ops prompt-test tab and snapshot API (Phase 4)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from chess_harness.accuracy_elo_map import map_path
from chess_harness.game_manager import GameManager
from chess_harness.prompt_test_ops import build_prompt_test_snapshot

from conftest import FIXTURES

LOOPBACK = {"Host": "127.0.0.1:8765"}
PUBLIC = {"Host": "example.com"}


def _harness_setup(tmp_path, monkeypatch) -> Path:
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))
    return harness_dir


def _write_packed_result(
    harness_dir: Path,
    *,
    game_id: str,
    prompt_pack: str,
    result: str,
    agent_color: str = "WHITE",
    accuracy: float | None = None,
    play_rating: float | None = None,
    ts: str | None = None,
) -> None:
    row: dict = {
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "game_id": game_id,
        "model_name": "composer-2.5",
        "agent_color": agent_color,
        "result": result,
        "prompt_pack": prompt_pack,
        "rated": False,
    }
    if accuracy is not None:
        row["accuracy"] = accuracy
    if play_rating is not None:
        row["play_rating"] = play_rating
    results_file = harness_dir / "results.jsonl"
    with results_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _write_live_packed_game(
    gm: GameManager,
    game_id: str,
    prompt_pack: str,
    *,
    last_activity: str | None = None,
) -> None:
    state = {
        "game_id": game_id,
        "status": "in_progress",
        "agent_color": "WHITE",
        "model_name": "composer-2.5",
        "moves": [],
        "prompt_pack": prompt_pack,
        "prompt_pack_hash": "abc",
        "prompt_pack_kind": "overlay",
        "last_activity": last_activity or datetime.now(timezone.utc).isoformat(),
    }
    gm.get_game_dir(game_id).mkdir(parents=True, exist_ok=True)
    gm.save_state(game_id, state)


def _write_warm_map(cal_root: Path, knots: list) -> None:
    cal_root.mkdir(parents=True, exist_ok=True)
    map_path(cal_root).write_text(
        json.dumps(
            {
                "engine_count": 2,
                "min_engines": 2,
                "knots": knots,
                "fitted_at": "2026-01-01T00:00:00.000Z",
            }
        ),
        encoding="utf-8",
    )


def test_prompt_test_snapshot_two_packs(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    gm = GameManager(str(harness_dir))

    _write_packed_result(
        harness_dir,
        game_id="packed-a-win",
        prompt_pack="a",
        result="1-0",
        accuracy=80.0,
        play_rating=1200.0,
        ts="2026-01-02T12:00:00+00:00",
    )
    _write_packed_result(
        harness_dir,
        game_id="packed-b-loss",
        prompt_pack="b",
        result="0-1",
        agent_color="WHITE",
        accuracy=70.0,
        play_rating=1100.0,
        ts="2026-01-02T13:00:00+00:00",
    )
    _write_packed_result(
        harness_dir,
        game_id="packed-a-no-result",
        prompt_pack="a",
        result="*",
        ts="2026-01-02T14:00:00+00:00",
    )
    _write_live_packed_game(
        gm,
        "live-a",
        "a",
        last_activity="2026-01-02T15:00:00+00:00",
    )

    cal_root = tmp_path / "cal"
    _write_warm_map(
        cal_root,
        [
            {"accuracy": 50.0, "elo": 500.0},
            {"accuracy": 90.0, "elo": 900.0},
        ],
    )

    payload = build_prompt_test_snapshot(base_dir=harness_dir, cal_root=cal_root)
    assert payload["ok"] is True
    packs = {row["id"]: row for row in payload["packs"]}
    assert len(packs) == 2

    pack_a = packs["a"]
    assert pack_a["title"] == "A Baseline"
    assert pack_a["in_progress"] == 1
    assert pack_a["finished"] == 1
    assert pack_a["wins"] == 1
    assert pack_a["draws"] == 0
    assert pack_a["losses"] == 0
    assert pack_a["mean_accuracy"] == 80.0
    assert pack_a["mean_play_rating"] == 800.0
    assert "live-a" in pack_a["recent_game_ids"]

    pack_b = packs["b"]
    assert pack_b["title"] == "B Verify"
    assert pack_b["in_progress"] == 0
    assert pack_b["finished"] == 1
    assert pack_b["wins"] == 0
    assert pack_b["draws"] == 0
    assert pack_b["losses"] == 1
    assert pack_b["mean_accuracy"] == 70.0
    assert pack_b["mean_play_rating"] == 700.0


def test_prompt_test_snapshot_five_pack_ids(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    pack_ids = ["a", "b", "c", "d", "f"]
    for idx, pack_id in enumerate(pack_ids):
        _write_packed_result(
            harness_dir,
            game_id=f"game-{pack_id}",
            prompt_pack=pack_id,
            result="1/2-1/2",
            ts=f"2026-01-0{idx + 1}T10:00:00+00:00",
        )

    payload = build_prompt_test_snapshot(base_dir=harness_dir)
    assert payload["ok"] is True
    assert len(payload["packs"]) == 5
    titles = {row["id"]: row["title"] for row in payload["packs"]}
    assert titles["a"] == "A Baseline"
    assert titles["b"] == "B Verify"
    assert titles["c"] == "C Principles"
    assert titles["d"] == "D Slow"
    assert titles["f"] == "f"


def test_prompt_test_snapshot_empty(tmp_path, monkeypatch):
    harness_dir = _harness_setup(tmp_path, monkeypatch)
    payload = build_prompt_test_snapshot(base_dir=harness_dir)
    assert payload == {"ok": True, "packs": []}


def test_prompt_test_api_loopback_only(spectator_client):
    client = spectator_client
    denied = client.get("/api/ops/prompt-test")
    assert denied.status_code == 403
    denied_public = client.get("/api/ops/prompt-test", headers=PUBLIC)
    assert denied_public.status_code == 403

    ok = client.get("/api/ops/prompt-test", headers=LOOPBACK)
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert "packs" in body


def test_prompt_test_api_with_fixture_results(harness_client):
    client, harness_dir = harness_client
    _write_packed_result(
        harness_dir,
        game_id="api-packed-a",
        prompt_pack="a",
        result="1-0",
        accuracy=85.0,
        play_rating=1250.0,
    )
    _write_packed_result(
        harness_dir,
        game_id="api-packed-c",
        prompt_pack="c",
        result="0-1",
        agent_color="BLACK",
        accuracy=75.0,
        play_rating=1150.0,
    )

    resp = client.get("/api/ops/prompt-test", headers=LOOPBACK)
    assert resp.status_code == 200
    packs = {row["id"]: row for row in resp.json()["packs"]}
    assert len(packs) == 2
    assert packs["a"]["title"] == "A Baseline"
    assert packs["c"]["wins"] == 1
    assert packs["c"]["losses"] == 0


def test_ops_html_has_prompt_test_tab(spectator_client):
    client = spectator_client
    resp = client.get("/ops/", headers=LOOPBACK)
    assert resp.status_code == 200
    assert "A/B" in resp.text
    assert "data-ops-tab=\"prompt-test\"" in resp.text
    assert "data-ops-section=\"prompt-test\"" in resp.text
    assert "data-prompt-test-body" in resp.text
