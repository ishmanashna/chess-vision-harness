"""Tests for Create Game static shell and API-backed create flow."""

from __future__ import annotations

from pathlib import Path

from chess_harness.game_manager import GameManager

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SITE = REPO_ROOT / "public-site"


def test_home_serves_public_shell(create_client):
    client, _ = create_client
    resp = client.get("/")
    assert resp.status_code == 200
    assert "What this is" in resp.text
    assert 'data-leaderboard' in resp.text
    assert "site-header" in resp.text


def test_legacy_tab_active_redirects_to_spectator(create_client):
    client, _ = create_client
    resp = client.get("/?tab=active", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/spectator/"


def test_legacy_tab_done_redirects_to_spectator_completed(create_client):
    client, _ = create_client
    resp = client.get("/?tab=done", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/spectator/?tab=completed"


def test_leaderboard_and_contact_serve_static(create_client):
    client, _ = create_client
    for path in ("/leaderboard/", "/contact/"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "site-header" in resp.text


def test_public_data_and_favicons_served(create_client):
    client, _ = create_client
    assert client.get("/data/leaderboard.json").status_code == 200
    assert client.get("/favicon.ico").status_code == 200
    assert client.get("/favicon.svg").status_code == 200
    assert client.get("/favicon-alert.svg").status_code == 200


def test_legacy_launcher_pages_redirect_to_launch_flows(create_client):
    client, _ = create_client
    for path, location in (
        ("/create", "/launch/?flow=engine"),
        ("/create/", "/launch/?flow=engine"),
        ("/create?mode=engine", "/launch/?flow=engine"),
        ("/create?mode=human", "/launch/?flow=playground"),
        ("/create?mode=avh", "/launch/?flow=playground"),
        ("/create?mode=avaa", "/launch/?flow=avaa"),
        ("/human", "/launch/?flow=playground"),
        ("/human/", "/launch/?flow=playground"),
        ("/puzzles", "/launch/?flow=puzzles"),
        ("/puzzles/", "/launch/?flow=puzzles"),
        ("/identify", "/launch/?flow=identify"),
        ("/identify/", "/launch/?flow=identify"),
        ("/lobby", "/launch/?flow=avaa"),
        ("/lobby/", "/launch/?flow=avaa"),
    ):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 301
        assert resp.headers["location"] == location


def test_launch_serves_static_shell(create_client):
    client, _ = create_client
    resp = client.get("/launch/")
    assert resp.status_code == 200
    assert "site-header" in resp.text
    assert "data-launch-page" in resp.text


def test_legacy_launcher_pages_deleted(create_client):
    for rel in (
        "create/index.html",
        "human/index.html",
        "puzzles/index.html",
        "js/create.js",
        "js/create-human.js",
        "js/puzzle-launcher.js",
    ):
        assert not (PUBLIC_SITE / rel).exists(), f"{rel} should be deleted"


def test_create_pairing_tabs_gated_to_avaa(create_client):
    """Find match / Direct chrome is AvA-only; CSS must honor [hidden]."""
    client, _ = create_client
    html = client.get("/launch/").text
    assert 'data-launch-pairing="find"' in html
    assert 'data-launch-pairing="direct"' in html
    assert "Rated game vs engine" in html

    css = (PUBLIC_SITE / "css" / "site.css").read_text(encoding="utf-8")
    assert "[hidden]" in css
    assert "display: none !important" in css


def test_create_game_via_api_v1(create_client):
    client, harness_dir = create_client

    reg = client.post("/api/v1/agents", json={"id": "composer-2.5"})
    assert reg.status_code == 200
    api_key = reg.json()["api_key"]

    create = client.post(
        "/api/v1/games",
        headers={"Authorization": f"Bearer {api_key}"},
        json={},
    )
    assert create.status_code == 200
    assert create.json()["ok"] is True
    assert "game_id" in create.json()

    keys_file = harness_dir / "api_keys.json"
    assert keys_file.exists()
    assert "composer-2.5" in keys_file.read_text(encoding="utf-8")

    games = client.get("/api/games").json()["games"]
    assert any(g["status"] == "in_progress" for g in games)


def test_legacy_post_create_removed(create_client):
    client, _ = create_client
    resp = client.post("/create", data={"model_id": "composer-2.5"})
    assert resp.status_code == 405
