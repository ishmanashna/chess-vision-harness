"""Contact form POST + localhost inbox API."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES
from chess_harness.contact_api import _events
from chess_harness.game_manager import GameManager
from chess_harness.spectator import app

LOOPBACK = {"Host": "127.0.0.1:8765"}
PUBLIC = {"Host": "example.com"}


@pytest.fixture
def contact_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))

    import chess_harness.spectator as spec

    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None
    _events.clear()

    client = TestClient(app)
    yield client, harness_dir
    _events.clear()
    spec._game_service = None
    spec._controller = None


def test_contact_page_has_form(contact_client):
    client, _ = contact_client
    resp = client.get("/contact/")
    assert resp.status_code == 200
    assert 'data-contact-form' in resp.text
    assert 'data-contact-inbox' in resp.text
    assert "/js/contact.js" in resp.text


def test_contact_submit_writes_inbox(contact_client):
    client, harness_dir = contact_client
    resp = client.post(
        "/api/contact",
        json={"sender": "Ada", "message": "Hello from the form"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["id"].startswith("msg-")
    inbox = harness_dir / "inbox"
    files = list(inbox.glob("msg-*.json"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "Ada" in text
    assert "Hello from the form" in text


def test_contact_submit_validates(contact_client):
    client, _ = contact_client
    empty = client.post("/api/contact", json={"sender": " ", "message": "hi"})
    assert empty.status_code == 400
    assert empty.json()["ok"] is False


def test_inbox_localhost_only(contact_client):
    client, _ = contact_client
    client.post("/api/contact", json={"sender": "Bob", "message": "Ping"})
    denied = client.get("/api/contact/inbox", headers=PUBLIC)
    assert denied.status_code == 403
    ok = client.get("/api/contact/inbox", headers=LOOPBACK)
    assert ok.status_code == 200
    data = ok.json()
    assert data["ok"] is True
    assert len(data["messages"]) == 1
    assert data["messages"][0]["sender"] == "Bob"


def test_inbox_mark_read_and_delete(contact_client):
    client, harness_dir = contact_client
    created = client.post(
        "/api/contact", json={"sender": "Cara", "message": "Please delete me"}
    ).json()
    mid = created["id"]
    read = client.post(f"/api/contact/inbox/{mid}/read", headers=LOOPBACK)
    assert read.status_code == 200
    assert read.json()["message"]["read"] is True
    listed = client.get("/api/contact/inbox", headers=LOOPBACK).json()
    assert listed["messages"][0]["read"] is True
    deleted = client.delete(f"/api/contact/inbox/{mid}", headers=LOOPBACK)
    assert deleted.status_code == 200
    assert not (harness_dir / "inbox" / f"{mid}.json").exists()
    empty = client.get("/api/contact/inbox", headers=LOOPBACK).json()
    assert empty["messages"] == []


def test_contact_rate_limit(contact_client):
    client, _ = contact_client
    for i in range(5):
        resp = client.post(
            "/api/contact",
            json={"sender": "Spam", "message": f"msg {i}"},
        )
        assert resp.status_code == 200
    blocked = client.post(
        "/api/contact",
        json={"sender": "Spam", "message": "one too many"},
    )
    assert blocked.status_code == 429
    assert blocked.json()["ok"] is False
