"""Phase 7: interactive move-list scrubbing + historical ply eval (no FEN leak)."""

from __future__ import annotations

import shutil
from pathlib import Path

import chess
import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, LOW_OPPONENT

from chess_harness.game_manager import GameManager
from chess_harness.move_rows import fen_at_ply
from chess_harness.spectator import app
from chess_harness.spectator_game_page import load_game_view_shell

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_JS = REPO_ROOT / "public-site" / "js"

_FORBIDDEN_EVAL_KEYS = frozenset({"fen", "board_fen", "start_fen", "moves"})


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.fixture
def phase7_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))

    import chess_harness.api_limits as api_limits
    import chess_harness.spectator as spec

    api_limits.get_limit_enforcer().reset_counters()
    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None
    spec._eval_cache.clear()
    spec._finished_eval_cache.clear()

    def fake_eval(fen: str):
        # Deterministic, position-dependent score (differs across plies).
        placement = fen.split()[0]
        return (sum(ord(c) for c in placement) % 701) - 350

    monkeypatch.setattr(spec, "_eval_position", fake_eval)

    client = TestClient(app)
    yield client, spec
    api_limits.get_limit_enforcer().reset_counters()
    spec._game_service = None
    spec._controller = None
    if spec._engine is not None:
        spec._engine.quit()
        spec._engine = None


def _register_and_play(client: TestClient) -> tuple[str, str]:
    reg = client.post("/api/v1/agents", json={"id": "phase7-agent", "name": "Phase7"})
    assert reg.status_code == 200, reg.text
    api_key = reg.json()["api_key"]
    create = client.post(
        "/api/v1/games",
        headers=_auth(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert create.status_code == 200, create.text
    game_id = create.json()["game_id"]
    # Agent e2e4; engine replies — enough plies for historical vs tip.
    mv = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))
    assert mv.status_code == 200, mv.text
    return game_id, api_key


def test_fen_at_ply_rebuilds_server_side():
    state = {
        "start_fen": chess.STARTING_FEN,
        "moves": ["e2e4", "e7e5", "g1f3"],
    }
    assert fen_at_ply(state, 0) == chess.STARTING_FEN
    after1 = fen_at_ply(state, 1)
    assert "4P3" in after1.split()[0]
    assert fen_at_ply(state, 99).split()[0] == fen_at_ply(state, 3).split()[0]


def test_eval_ply_no_fen_and_scores_differ(phase7_client):
    client, spec = phase7_client
    game_id, _ = _register_and_play(client)

    tip = client.get(f"/api/games/{game_id}/eval")
    assert tip.status_code == 200
    tip_body = tip.json()
    assert tip_body["ok"] is True
    assert "score" in tip_body
    assert tip_body.get("eval_ui") is not None
    assert not (_FORBIDDEN_EVAL_KEYS & tip_body.keys())

    # Poison tip cache — historical ply must ignore last_eval_cp.
    state = spec.game_manager.load_state(game_id)
    assert state is not None
    tip_ply = len(state.get("moves", []))
    assert tip_ply >= 1
    state["last_eval_cp"] = 99999
    spec.game_manager.save_state(game_id, state)

    hist = client.get(f"/api/games/{game_id}/eval", params={"ply": 1})
    assert hist.status_code == 200
    hist_body = hist.json()
    assert hist_body["ok"] is True
    assert not (_FORBIDDEN_EVAL_KEYS & hist_body.keys())
    assert "fen" not in hist_body
    assert "board_fen" not in hist_body
    assert "start_fen" not in hist_body
    assert hist_body["score"] != 99999

    start = client.get(f"/api/games/{game_id}/eval", params={"ply": 0})
    assert start.status_code == 200
    start_body = start.json()
    assert start_body["ok"] is True
    assert not (_FORBIDDEN_EVAL_KEYS & start_body.keys())

    # Distinct positions → distinct fake scores (start vs after e2e4 vs tip).
    assert start_body["score"] != hist_body["score"]

    tip_again = client.get(f"/api/games/{game_id}/eval")
    assert tip_again.json()["score"] == 99999  # tip still uses last_eval_cp


def test_api_v1_moves_still_404(phase7_client):
    client, _ = phase7_client
    game_id, api_key = _register_and_play(client)
    resp = client.get(f"/api/v1/games/{game_id}/moves", headers=_auth(api_key))
    assert resp.status_code == 404


def test_spectator_game_js_data_ply_and_scrub():
    game_js = (PUBLIC_JS / "spectator-game.js").read_text(encoding="utf-8")
    assert "data-ply" in game_js
    assert "setViewPly" in game_js
    assert "scrubToPly" in game_js
    assert "EVAL_DEBOUNCE_MS" in game_js
    assert "?ply=" in game_js
    assert "moveIncreased" in game_js
    assert "syncTip" in game_js
    board_js = (PUBLIC_JS / "spectator-board.js").read_text(encoding="utf-8")
    assert "setViewPly" in board_js
    assert "syncTip" in board_js


def test_spectator_page_selected_ply_css():
    html = load_game_view_shell()
    watch_css = (REPO_ROOT / "public-site" / "css" / "watch.css").read_text(encoding="utf-8")
    assert ".move-row .w.on" in watch_css
    assert "cursor: pointer" in watch_css
    assert 'type="module" src="/js/spectator-game.js"' in html
