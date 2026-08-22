"""Operator panel Phase 4: Umami audience API and public-site tracker."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from chess_harness import ops_audience

LOOPBACK = {"Host": "127.0.0.1:8765"}
PUBLIC = {"Host": "example.com"}
REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_SITE = REPO_ROOT / "public-site"


def test_audience_loopback_only(spectator_client):
    client = spectator_client
    assert client.get("/api/ops/audience").status_code == 404
    assert client.get("/api/ops/audience", headers=PUBLIC).status_code == 404
    ok = client.get("/api/ops/audience", headers=LOOPBACK)
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert body["configured"] is False
    assert body["referrers"] == []
    assert body["pages"] == []
    assert body["countries"] == []
    assert "CHESS_HARNESS_UMAMI_TOKEN" in body["message"]


def test_audience_missing_env_no_fake_referrers(spectator_client, monkeypatch):
    monkeypatch.delenv("CHESS_HARNESS_UMAMI_TOKEN", raising=False)
    monkeypatch.delenv("CHESS_HARNESS_UMAMI_WEBSITE_ID", raising=False)
    ops_audience.reset_audience_cache()

    body = spectator_client.get("/api/ops/audience", headers=LOOPBACK).json()
    assert body["configured"] is False
    assert body["pageviews"] is None
    assert body["visitors"] is None
    assert body["referrers"] == []
    assert body["pages"] == []
    assert body["countries"] == []


def test_audience_with_mocked_umami(spectator_client, monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_UMAMI_TOKEN", "test-token")
    monkeypatch.setenv("CHESS_HARNESS_UMAMI_WEBSITE_ID", "site-uuid")
    monkeypatch.setenv("CHESS_HARNESS_UMAMI_API_HOST", "https://umami.test/v1")
    ops_audience.reset_audience_cache()

    calls: list[str] = []

    def fake_fetch(url: str, token: str) -> object:
        calls.append(url)
        assert token == "test-token"
        if url.endswith("/stats?startAt=61000&endAt=86461000"):
            return {"pageviews": 42, "visitors": 17}
        if "type=referrer" in url:
            return [{"x": "google.com", "y": 5}, {"x": "", "y": 3}]
        if "type=path" in url:
            return [{"x": "/", "y": 10}, {"x": "/launch/", "y": 4}]
        if "type=country" in url:
            return [{"x": "US", "y": 8}, {"x": "DE", "y": 2}]
        raise AssertionError(f"unexpected url {url}")

    real_fetch = ops_audience.fetch_audience_from_umami

    def fake_pull(*, token, website_id, api_base, now_ms=None, http_fetch=ops_audience._fetch_json):
        return real_fetch(
            token=token,
            website_id=website_id,
            api_base=api_base,
            now_ms=86461000,
            http_fetch=fake_fetch,
        )

    monkeypatch.setattr(ops_audience, "fetch_audience_from_umami", fake_pull)

    body = spectator_client.get("/api/ops/audience", headers=LOOPBACK).json()
    assert body["configured"] is True
    assert body["pageviews"] == 42
    assert body["visitors"] == 17
    assert body["referrers"][0] == {"name": "google.com", "visitors": 5}
    assert body["referrers"][1] == {"name": "direct", "visitors": 3}
    assert body["pages"][0] == {"path": "/", "visitors": 10}
    assert body["countries"][0] == {"code": "US", "visitors": 8}
    assert len(calls) == 4
    assert any("/stats?" in url for url in calls)


def test_audience_cache_skips_second_fetch(spectator_client, monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_UMAMI_TOKEN", "test-token")
    monkeypatch.setenv("CHESS_HARNESS_UMAMI_WEBSITE_ID", "site-uuid")
    ops_audience.reset_audience_cache()

    calls = {"n": 0}

    def fake_fetch(_url: str, _token: str) -> dict:
        calls["n"] += 1
        return {
            "pageviews": 1,
            "visitors": 1,
            "referrers": [],
            "pages": [],
            "countries": [],
        }

    def fake_pull(**kwargs):
        calls["n"] += 1
        return {
            "ok": True,
            "configured": True,
            "message": None,
            "pageviews": 9,
            "visitors": 4,
            "referrers": [{"name": "direct", "visitors": 4}],
            "pages": [{"path": "/", "visitors": 4}],
            "countries": [{"code": "US", "visitors": 4}],
            "source": "umami",
            "cached": False,
        }

    monkeypatch.setattr(ops_audience, "fetch_audience_from_umami", fake_pull)

    client = spectator_client
    first = client.get("/api/ops/audience", headers=LOOPBACK).json()
    second = client.get("/api/ops/audience", headers=LOOPBACK).json()

    assert first["cached"] is False
    assert second["cached"] is True
    assert calls["n"] == 1


def test_audience_cache_expires_after_60s(monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_UMAMI_TOKEN", "test-token")
    monkeypatch.setenv("CHESS_HARNESS_UMAMI_WEBSITE_ID", "site-uuid")
    ops_audience.reset_audience_cache()

    calls = {"n": 0}

    def fake_pull(**_kwargs):
        calls["n"] += 1
        return {
            "ok": True,
            "configured": True,
            "message": None,
            "pageviews": 1,
            "visitors": 1,
            "referrers": [],
            "pages": [],
            "countries": [],
            "source": "umami",
            "cached": False,
        }

    monkeypatch.setattr(ops_audience, "fetch_audience_from_umami", fake_pull)

    t0 = 1_700_000_000.0
    first = ops_audience.audience_snapshot(now=t0)
    second = ops_audience.audience_snapshot(now=t0 + 30)
    third = ops_audience.audience_snapshot(now=t0 + 61)

    assert first["cached"] is False
    assert second["cached"] is True
    assert third["cached"] is False
    assert calls["n"] == 2


@pytest.mark.parametrize(
    "pattern",
    [
        r"Bearer\s+[A-Za-z0-9._-]{8,}",
        r"CHESS_HARNESS_UMAMI_TOKEN",
    ],
)
def test_public_site_files_do_not_contain_secrets(pattern):
    roots = [
        PUBLIC_SITE / "js",
        PUBLIC_SITE / "ops",
        PUBLIC_SITE / "index.html",
        PUBLIC_SITE / "launch" / "index.html",
        PUBLIC_SITE / "contact" / "index.html",
        PUBLIC_SITE / "leaderboard" / "index.html",
    ]
    rx = re.compile(pattern)
    hits: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if not path.is_file():
                continue
            if path.suffix not in {".js", ".html", ".css"}:
                continue
            text = path.read_text(encoding="utf-8")
            if rx.search(text):
                hits.append(str(path.relative_to(REPO_ROOT)))
    assert hits == []
