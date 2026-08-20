"""Shared FastAPI TestClient setup for spectator harness integration tests."""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from chess_harness.game_manager import GameManager
from chess_harness.spectator import app

_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def testclient_transport(client: TestClient):
    """Map agent_http transport calls onto a FastAPI TestClient (query string preserved)."""

    def transport(method: str, url: str, headers, body=None):
        parsed = urlparse(url)
        path = parsed.path
        if parsed.query:
            path = f"{path}?{parsed.query}"
        hdrs = dict(headers)
        if method.upper() == "GET":
            resp = client.get(path, headers=hdrs)
        elif method.upper() == "POST":
            if body is not None:
                resp = client.post(path, headers=hdrs, content=body)
            else:
                resp = client.post(path, headers=hdrs)
        else:
            raise ValueError(f"unsupported method {method}")
        return resp.status_code, dict(resp.headers), resp.content

    return transport


def configure_spectator_harness(harness_dir: Path, monkeypatch) -> Path:
    """Point the spectator app at an isolated harness directory."""
    harness_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(_FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))
    monkeypatch.setenv("CHESS_HARNESS_CALIBRATION_IN_PROCESS", "1")

    import chess_harness.api_limits as api_limits
    import chess_harness.spectator as spec

    api_limits.get_limit_enforcer().reset_counters()
    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None
    return harness_dir


def teardown_spectator_harness() -> None:
    import chess_harness.api_limits as api_limits
    import chess_harness.spectator as spec

    api_limits.get_limit_enforcer().reset_counters()
    spec._game_service = None
    spec._controller = None
    if spec._engine is not None:
        spec._engine.quit()
        spec._engine = None
    try:
        if hasattr(spec, "_get_controller"):
            spec._get_controller().opponent_mgr.release()
    except Exception:
        pass


def make_test_client() -> TestClient:
    return TestClient(app)
