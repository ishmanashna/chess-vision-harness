"""One evidence selection for summary, pagination, chats, and safe run views."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from chess_harness.prompt_test_ops import build_prompt_test_snapshot
from chess_harness.ops_experiment_runs import list_experiment_runs, run_artifact_view, run_game_links
from chess_harness.ops_metrics import MetricsRing


def write_rows(root, rows):
    root.mkdir(exist_ok=True)
    (root / "results.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def row(gid, pack="a", **extra):
    return {"game_id": gid, "prompt_pack": pack, "model_name": "model-1", "agent_color": "WHITE",
            "result": "1-0", "accuracy": 80, "opponent_id": "random", "ts": "2026-10-13T12:00:00Z", **extra}


def test_default_family_applies_to_games_counts_and_chats(tmp_path):
    write_rows(tmp_path, [row("composer"), row("jeff", "j1")])
    for gid in ("composer", "jeff", "unrelated"):
        p = tmp_path / "prompt_test" / gid
        p.mkdir(parents=True)
        (p / "thread.json").write_text('{"messages": [{"text": "fixture"}]}', encoding="utf-8")
    for family, gid in [(None, "composer"), ("jeff", "jeff")]:
        payload = build_prompt_test_snapshot(family, base_dir=tmp_path)
        assert {g["game_id"] for g in payload["games"]} == {gid}
        assert {g["game_id"] for g in payload["chats"]} == {gid}
        assert payload["summary"]["finished"] == sum(p["finished"] for p in payload["packs"]) == 1


def test_deduplication_filters_and_explicit_page_totals(tmp_path):
    rows = [row(f"g-{i}", run_id="run-a") for i in range(105)]
    rows += [rows[0], row("other-run", run_id="run-b"), row("other-model", model_name="model-2")]
    write_rows(tmp_path, rows)
    payload = build_prompt_test_snapshot(base_dir=tmp_path, run_id="run-a", model="model-1", pack="a", opponent="random", status="finished")
    assert payload["total"] == payload["summary"]["finished"] == payload["packs"][0]["finished"] == 105
    assert len(payload["games"]) == 100 and payload["has_more"]
    second = build_prompt_test_snapshot(base_dir=tmp_path, run_id="run-a", offset=100)
    assert len(second["games"]) == 5 and not second["has_more"]
    assert set(g["game_id"] for g in payload["games"]).isdisjoint(g["game_id"] for g in second["games"])


def test_failed_abandoned_excluded_and_missing_analysis_are_honest(tmp_path):
    write_rows(tmp_path, [row("excluded", prompt_test_excluded=True),
                          row("failed", result="*", status="failed"),
                          row("idle", result="*", end_reason="idle_timeout"),
                          row("unscored", result="*"), row("pending", accuracy=None)])
    data = build_prompt_test_snapshot(base_dir=tmp_path)
    assert data["summary"] == {"total": 5, "finished": 1, "in_progress": 0, "failed": 1,
                                "abandoned": 1, "excluded": 1, "no_result": 1, "analysed": 0}
    assert data["packs"][0]["mean_accuracy"] is None
    assert all(g["run_id"] == "legacy-unassigned" for g in data["games"])
    assert all(g["metric_reason"] for g in data["games"])


def test_scored_result_beats_stale_live_state(tmp_path):
    write_rows(tmp_path, [row("same")])
    game = tmp_path / "games" / "same"
    game.mkdir(parents=True)
    (game / "state.json").write_text(json.dumps(row("same", status="in_progress", result="*", moves=[])), encoding="utf-8")
    data = build_prompt_test_snapshot(base_dir=tmp_path)
    assert data["summary"]["finished"] == 1
    assert data["summary"]["in_progress"] == 0


def test_runs_only_expose_safe_fields_not_raw_artifacts(tmp_path):
    directory = tmp_path / "experiments" / "fixture" / "runs" / "one"
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps({"schema_version": 1, "experiment_id": "fixture",
        "run_id": "one", "model": "model", "provider": "fixture", "api_key": "PRIVATE", "reason": "PRIVATE"}), encoding="utf-8")
    (directory / "report.md").write_text("PRIVATE", encoding="utf-8")
    (directory / "events.jsonl").write_text(json.dumps({"event": "move_accepted", "game_id": "game-1",
        "reason": "PRIVATE", "request_headers": "PRIVATE", "model": "Bearer abcdefghijklmnop"}) + "\n", encoding="utf-8")
    runs = list_experiment_runs(tmp_path)["runs"]
    key = runs[0]["key"]
    for kind in ("report", "events"):
        payload = run_artifact_view(key, kind, tmp_path)
        assert "PRIVATE" not in json.dumps(payload)
        assert "Bearer abcdefghijklmnop" not in json.dumps(payload)
    assert run_game_links(tmp_path) == {"game-1": "one"}
    with pytest.raises(FileNotFoundError):
        run_artifact_view("../../outside", "events", tmp_path)


def test_operator_health_and_static_are_separate_from_product_traffic():
    ring = MetricsRing()
    for path in ("/api/ops/snapshot", "/health", "/js/ops.js", "/api/v1/games/g/status", "/g/g"):
        ring.record(path=path, method="GET", status=200, duration_ms=1)
    snapshot = ring.snapshot()
    assert snapshot["origin_requests_24h"] == 5
    assert snapshot["product_requests_24h"] == 2
    assert sum(row["requests"] for row in snapshot["routes"]) == 5


def test_api_validation_and_artifact_loopback_lock(spectator_client):
    client = spectator_client
    headers = {"Host": "127.0.0.1:8765"}
    assert client.get("/api/ops/prompt-test?family=invalid", headers=headers).status_code == 422
    assert client.get("/api/ops/prompt-test?offset=-1", headers=headers).status_code == 422
    assert client.get("/api/ops/experiments", headers={"Host": "example.com"}).status_code == 404
    assert client.get("/api/ops/experiments/unknown/events", headers=headers).status_code == 404


def test_audience_requests_do_not_duplicate_a_running_provider_fetch(monkeypatch):
    import threading
    from chess_harness import ops_audience

    monkeypatch.setenv("CHESS_HARNESS_UMAMI_TOKEN", "fixture")
    monkeypatch.setenv("CHESS_HARNESS_UMAMI_WEBSITE_ID", "fixture")
    ops_audience.reset_audience_cache()
    started, release = threading.Event(), threading.Event()
    calls = []

    def slow(**_kwargs):
        calls.append(True)
        started.set()
        release.wait(2)
        return {"ok": True, "configured": True, "visitors": 1}

    monkeypatch.setattr(ops_audience, "fetch_audience_from_umami", slow)
    worker = threading.Thread(target=ops_audience.audience_snapshot)
    worker.start()
    try:
        assert started.wait(1)
        second = ops_audience.audience_snapshot()
        assert second["refreshing"] is True
        assert second["visitors"] is None
        assert len(calls) == 1
    finally:
        release.set()
        worker.join(3)
        ops_audience.reset_audience_cache()
