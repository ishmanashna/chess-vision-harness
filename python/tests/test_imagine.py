"""Phase 4 — Imagine API: hypothetical lines without mutating game state."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import LOW_OPPONENT
from harness_client import auth_headers
from leak_guards import assert_imagine_no_leaks

from chess_harness.game_manager import GameManager


def _auth(api_key: str) -> dict[str, str]:
    return auth_headers(api_key)


def _register(client: TestClient, model_id: str = "imagine-agent") -> str:
    reg = client.post("/api/v1/agents", json={"id": model_id, "name": model_id})
    assert reg.status_code == 200
    return reg.json()["api_key"]


def _create_ave(client: TestClient, api_key: str) -> str:
    create = client.post(
        "/api/v1/games",
        headers=_auth(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert create.status_code == 200, create.text
    return create.json()["game_id"]


def _snapshot(harness_dir: Path, game_id: str) -> tuple[dict, bytes, list]:
    gm = GameManager(str(harness_dir))
    state = gm.load_state(game_id)
    assert state is not None
    board_bytes = gm.get_board_path(game_id).read_bytes()
    return copy.deepcopy(state), board_bytes, list(state.get("move_audit") or [])


def test_imagine_legal_sequence_ave(api_client):
    client, harness_dir = api_client
    api_key = _register(client)
    game_id = _create_ave(client, api_key)
    before_state, before_png, before_audit = _snapshot(harness_dir, game_id)

    resp = client.post(
        f"/api/v1/games/{game_id}/imagine",
        headers=_auth(api_key),
        json={"moves": ["e2e4", "e7e5", "g1f3"]},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.headers.get("X-Imagine") == "1"
    assert resp.headers.get("X-Imagine-Plies") == "3"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert resp.content != before_png

    after_state, after_png, after_audit = _snapshot(harness_dir, game_id)
    assert after_state == before_state
    assert after_png == before_png
    assert after_audit == before_audit
    assert after_state.get("last_activity") == before_state.get("last_activity")
    assert after_state.get("moves") == before_state.get("moves")


def test_imagine_illegal_mid_sequence(api_client):
    client, harness_dir = api_client
    api_key = _register(client, "imagine-bad")
    game_id = _create_ave(client, api_key)
    before_state, before_png, before_audit = _snapshot(harness_dir, game_id)

    resp = client.post(
        f"/api/v1/games/{game_id}/imagine",
        headers=_auth(api_key),
        json={"moves": ["e2e4", "e7e5", "e2e4"]},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert data.get("index") == 2
    assert "error" in data
    assert_imagine_no_leaks(data)
    # Soft errors only — no legal-move dump
    assert "legal moves" not in data["error"].lower()

    after_state, after_png, after_audit = _snapshot(harness_dir, game_id)
    assert after_state == before_state
    assert after_png == before_png
    assert after_audit == before_audit


def test_imagine_too_many_plies(api_client):
    client, _ = api_client
    api_key = _register(client, "imagine-cap")
    game_id = _create_ave(client, api_key)
    resp = client.post(
        f"/api/v1/games/{game_id}/imagine",
        headers=_auth(api_key),
        json={"moves": ["e2e4"] * 13},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["ok"] is False
    assert "12" in data["error"]


def test_imagine_does_not_set_avh_joined(api_client, monkeypatch):
    client, harness_dir = api_client
    api_key = _register(client, "imagine-avh")
    import chess_harness.human_vs_agent as hva

    monkeypatch.setattr(hva.random, "choice", lambda _items: "WHITE")
    create = client.post(
        "/api/v1/games/human",
        headers=_auth(api_key),
        json={"nickname": "Bob"},
    )
    assert create.status_code == 200, create.text
    game_id = create.json()["game_id"]
    gm = GameManager(str(harness_dir))
    assert gm.load_state(game_id).get("agent_joined") is False

    resp = client.post(
        f"/api/v1/games/{game_id}/imagine",
        headers=_auth(api_key),
        json={"moves": ["e2e4"]},
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Imagine") == "1"
    state = gm.load_state(game_id)
    assert state.get("agent_joined") is False
    assert state.get("moves") == []


def test_imagine_avaa(api_client):
    client, harness_dir = api_client
    white = client.post("/api/v1/agents", json={"id": "img-w", "name": "W"})
    black = client.post("/api/v1/agents", json={"id": "img-b", "name": "B"})
    white_key = white.json()["api_key"]
    create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(white_key),
        json={"white_model_id": "img-w", "black_model_id": "img-b"},
    )
    assert create.status_code == 200, create.text
    game_id = create.json()["game_id"]
    before_state, before_png, _ = _snapshot(harness_dir, game_id)

    resp = client.post(
        f"/api/v1/games/{game_id}/imagine",
        headers=_auth(white_key),
        json={"moves": ["e2e4", "e7e5"]},
    )
    assert resp.status_code == 200
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"
    after_state, after_png, _ = _snapshot(harness_dir, game_id)
    assert after_state == before_state
    assert after_png == before_png


def test_cmd_imagine_temp_outside_game_dir(api_client, monkeypatch):
    client, harness_dir = api_client
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    api_key = _register(client, "imagine-cli")
    game_id = _create_ave(client, api_key)

    from chess_harness.commands import cmd_imagine

    before_state, before_png, _ = _snapshot(harness_dir, game_id)
    result = cmd_imagine(game_id, ["e2e4", "c7c5"])
    assert result["ok"] is True
    assert result["hypothetical"] is True
    assert result["applied_count"] == 2
    path = Path(result["imagine_path"])
    assert path.is_file()
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    game_dir = GameManager(str(harness_dir)).get_game_dir(game_id)
    assert game_dir.resolve() not in path.resolve().parents
    assert path.resolve() != GameManager(str(harness_dir)).get_board_path(game_id).resolve()

    after_state, after_png, _ = _snapshot(harness_dir, game_id)
    assert after_state == before_state
    assert after_png == before_png
    path.unlink(missing_ok=True)


def test_mcp_imagine_board_tool(api_client, monkeypatch):
    import asyncio
    import base64

    client, harness_dir = api_client
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    api_key = _register(client, "imagine-mcp")
    game_id = _create_ave(client, api_key)

    from chess_harness.game_service import GameService
    from chess_harness.tools_mcp import ChessHarnessMCP

    mcp = ChessHarnessMCP()
    mcp.game_manager = GameManager(str(harness_dir))
    mcp.game_service = GameService(mcp.game_manager)

    tools = {t.name: t for t in mcp.get_tools()}
    assert "chess_imagine_board" in tools

    async def run():
        return await mcp.handle_tool_call(
            "chess_imagine_board",
            {"game_id": game_id, "moves": ["e2e4"]},
        )

    result = asyncio.run(run())
    texts = [c for c in result if c.type == "text"]
    data = json.loads(texts[0].text)
    assert data["ok"] is True
    assert data["hypothetical"] is True
    images = [c for c in result if c.type == "image"]
    assert images
    assert base64.b64decode(images[0].data)[:8] == b"\x89PNG\r\n\x1a\n"
    Path(data["imagine_path"]).unlink(missing_ok=True)
