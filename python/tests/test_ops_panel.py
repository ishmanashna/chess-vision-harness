"""Operator panel Phase 1: loopback page, snapshot API, Pages contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from chess_harness.contact_inbox import append_message, list_messages
from chess_harness.ops_api import build_ops_snapshot
from harness_client import auth_headers

LOOPBACK = {"Host": "127.0.0.1:8765"}
PUBLIC = {"Host": "example.com"}


def test_ops_page_loopback_only(spectator_client):
    client = spectator_client
    denied = client.get("/ops/")
    assert denied.status_code == 404
    denied_plain = client.get("/ops")
    assert denied_plain.status_code == 404
    ok = client.get("/ops/", headers=LOOPBACK)
    assert ok.status_code == 200
    assert "Operator panel" in ok.text
    assert "/js/ops.js" in ok.text
    assert "data-ops-panel" in ok.text


def test_ops_snapshot_loopback_only(spectator_client):
    client = spectator_client
    denied = client.get("/api/ops/snapshot")
    assert denied.status_code == 403
    denied_public = client.get("/api/ops/snapshot", headers=PUBLIC)
    assert denied_public.status_code == 403
    ok = client.get("/api/ops/snapshot", headers=LOOPBACK)
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert "disk" in body
    assert "harness_dir" in body
    assert "health" in body
    assert body["health"]["ok"] is True
    assert "inbox" in body
    assert "activity" in body
    assert "live" in body
    assert "tunnel" in body
    metrics = body["metrics"]
    assert "origin_requests_24h" in metrics
    assert "error_rate" in metrics
    assert "buckets" in metrics
    assert "routes" in metrics
    assert metrics["storage"] == "in_memory"


def test_ops_snapshot_inbox_matches_contact(harness_client):
    client, harness_dir = harness_client
    append_message("Ops tester", "Unread ping", base_dir=harness_dir)
    append_message("Ops tester", "Second line", base_dir=harness_dir)
    messages = list_messages(base_dir=harness_dir)
    unread = sum(1 for row in messages if not row.get("read"))

    resp = client.get("/api/ops/snapshot", headers=LOOPBACK)
    assert resp.status_code == 200
    inbox = resp.json()["inbox"]
    assert inbox["unread"] == unread
    assert inbox["total"] == len(messages)
    assert inbox["latest"][0]["message"] == "Second line"


def test_build_ops_snapshot_disk_fields(tmp_path):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    (harness_dir / "note.txt").write_text("x" * 1024, encoding="utf-8")
    payload = build_ops_snapshot(base_dir=harness_dir, build_games_list=lambda *_a, **_k: ([], 0))
    assert payload["disk"]["total_bytes"] > 0
    assert payload["harness_dir"]["size_bytes"] >= 1024


def test_go_online_script_opens_ops_panel():
    text = Path(__file__).resolve().parents[2].joinpath("deploy", "go-online.ps1").read_text(
        encoding="utf-8"
    )
    assert "-NoPanel" in text
    assert "/ops/" in text
    assert "Start-Process" in text
    assert "leaving serve running" in text


def test_ops_metrics_count_origin_requests(spectator_client):
    client = spectator_client
    before = client.get("/api/ops/snapshot", headers=LOOPBACK).json()["metrics"]["origin_requests_24h"]
    client.get("/health")
    client.get("/launch/", headers=LOOPBACK)
    after = client.get("/api/ops/snapshot", headers=LOOPBACK).json()["metrics"]["origin_requests_24h"]
    assert after >= before + 2


def test_ops_metrics_records_5xx_event(spectator_client):
    client = spectator_client
    resp = client.get("/api/ops/test/force-5xx", headers=LOOPBACK)
    assert resp.status_code == 500
    metrics = client.get("/api/ops/snapshot", headers=LOOPBACK).json()["metrics"]
    assert metrics["errors"]["events_5xx"] >= 1
    assert any(ev["status"] == 500 for ev in metrics["errors"]["recent"])


def test_ops_illegal_move_not_outage(api_client):
    client, _harness_dir = api_client
    from conftest import LOW_OPPONENT

    reg = client.post("/api/v1/agents", json={"id": "ops-metrics-agent", "name": "Ops Metrics"})
    api_key = reg.json()["api_key"]
    create = client.post(
        "/api/v1/games",
        headers=auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    game_id = create.json()["game_id"]

    before = client.get("/api/ops/snapshot", headers=LOOPBACK).json()["metrics"]
    illegal = client.post(
        f"/api/v1/games/{game_id}/move/e2e5",
        headers=auth_headers(api_key),
    )
    assert illegal.status_code == 400

    metrics = client.get("/api/ops/snapshot", headers=LOOPBACK).json()["metrics"]
    assert metrics["routine_4xx_24h"] >= before["routine_4xx_24h"] + 1
    assert all(
        not (ev["status"] == 400 and "/move/" in ev["path"])
        for ev in metrics["errors"]["recent"]
    )
