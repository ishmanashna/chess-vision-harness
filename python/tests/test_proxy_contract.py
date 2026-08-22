"""Shared Pages proxy route contract and client-IP forwarding tests."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import FIXTURES, REPO_ROOT
from chess_harness.api_limits import ApiLimitEnforcer, AuthContext
from chess_harness.api_v1 import build_router
from chess_harness.game_manager import GameManager
from chess_harness.game_service import GameService
from chess_harness.limits import HarnessLimits

CONTRACT_PATH = REPO_ROOT / "public-site" / "functions" / "proxy-routes.contract.json"
PROXY_JS_PATH = REPO_ROOT / "public-site" / "functions" / "_proxy.js"
PROXY_HEADER_TEST = REPO_ROOT / "public-site" / "functions" / "proxy-header.test.mjs"


@pytest.fixture
def limit_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))

    game_manager = GameManager(str(harness_dir))

    def get_game_service() -> GameService:
        return GameService(game_manager=game_manager)

    tight = HarnessLimits(
        max_concurrent_games=2,
        max_engine_processes=12,
        max_games_per_hour_per_key=2,
        max_moves_per_hour_per_key=3,
        idle_timeout_sec=300,
        max_agent_registrations_per_ip_per_hour=2,
    )
    enforcer = ApiLimitEnforcer(tight)

    app = FastAPI()
    app.include_router(build_router(get_game_service, limit_enforcer=enforcer))
    client = TestClient(app)
    yield client, harness_dir, enforcer
    get_game_service().controller.opponent_mgr.release()


def _load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _is_watch_shell_html(pathname: str) -> bool:
    import re

    if re.match(r"^/(g|p|i)/[^/]+/?$", pathname):
        return True
    return bool(re.match(r"^/play/[^/]+/?$", pathname))


def _is_watch_asset_subpath(pathname: str) -> bool:
    import re

    return bool(re.match(r"^/(g|p|i)/[^/]+/.+", pathname))


def _should_proxy_path(pathname: str, contract: dict) -> bool:
    if pathname in contract["proxy_path_exact"]:
        return True
    return any(pathname.startswith(prefix) for prefix in contract["proxy_path_prefixes"])


def _should_proxy_to_origin(pathname: str, contract: dict) -> bool:
    if _is_watch_shell_html(pathname):
        return False
    if _is_watch_asset_subpath(pathname):
        return True
    return _should_proxy_path(pathname, contract)


def _is_calibration_path(pathname: str, contract: dict) -> bool:
    if pathname in contract["calibration_path_exact"]:
        return True
    return any(pathname.startswith(prefix) for prefix in contract["calibration_path_prefixes"])


def _is_puzzle_set_path(pathname: str, contract: dict) -> bool:
    if pathname in contract.get("puzzle_set_path_exact", []):
        return True
    if any(
        pathname.startswith(prefix)
        for prefix in contract.get("puzzle_set_api_path_prefixes", [])
    ):
        return True
    return any(pathname.startswith(prefix) for prefix in contract.get("puzzle_set_path_prefixes", []))


def _is_ops_path(pathname: str, contract: dict) -> bool:
    if pathname in contract.get("ops_path_exact", []):
        return True
    if any(pathname.startswith(prefix) for prefix in contract.get("ops_api_path_prefixes", [])):
        return True
    return any(pathname.startswith(prefix) for prefix in contract.get("ops_path_prefixes", []))


@pytest.fixture
def contract():
    return _load_contract()


def test_proxy_js_exports_watch_shell_helpers():
    text = PROXY_JS_PATH.read_text(encoding="utf-8")
    assert 'from "./proxy-routes.contract.js"' in text
    assert "buildProxyRequestHeaders" in text
    assert "isWatchShellHtml" in text
    assert "shouldProxyToOrigin" in text
    assert "fetchWatchShellHtml" in (
        REPO_ROOT / "public-site" / "functions" / "_watch_shell.js"
    ).read_text(encoding="utf-8")
    assert "fetchWatchShellHtml" in (
        REPO_ROOT / "public-site" / "functions" / "_middleware.js"
    ).read_text(encoding="utf-8")


def test_proxy_contract_js_matches_json():
    data = _load_contract()
    js_path = CONTRACT_PATH.with_suffix(".js")
    assert js_path.is_file()
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import c from './proxy-routes.contract.js'; process.stdout.write(JSON.stringify(c))",
        ],
        cwd=js_path.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == data

@pytest.mark.parametrize(
    "pathname",
    [
        "/api/v1/agents",
        "/api/v1/games",
        "/api/games",
        "/api/play/foo",
        "/api/contact",
        "/api/leaderboard/live",
        "/api/leaderboard/puzzles/live",
        "/api/leaderboard/identify/live",
        "/g/game-test/board.png",
        "/p/attempt-1/board.png",
        "/i/attempt-2/board.txt",
        "/g/game-test/answer.png",
    ],
)
def test_contract_proxy_paths(pathname, contract):
    assert _should_proxy_to_origin(pathname, contract)


@pytest.mark.parametrize(
    "pathname",
    [
        "/g/game-test",
        "/p/attempt-1",
        "/i/attempt-2",
        "/play/game-human",
    ],
)
def test_contract_watch_shell_html_not_proxied(pathname, contract):
    assert not _should_proxy_to_origin(pathname, contract)


@pytest.mark.parametrize(
    "pathname",
    [
        "/api/models",
        "/api/edge-health",
        "/api/calibration/status",
        "/calibration",
        "/leaderboard/",
    ],
)
def test_contract_non_proxy_paths(pathname, contract):
    assert not _should_proxy_to_origin(pathname, contract)


@pytest.mark.parametrize(
    "pathname",
    [
        "/calibration",
        "/calibration/",
        "/calibration/start",
        "/api/calibration",
        "/api/calibration/stop-all",
    ],
)
def test_contract_calibration_paths(pathname, contract):
    assert _is_calibration_path(pathname, contract)


@pytest.mark.parametrize(
    "pathname",
    [
        "/puzzle-set",
        "/puzzle-set/",
        "/api/puzzle-set",
        "/puzzle-set/pz-sample",
        "/api/puzzle-set/pz-sample/preview",
        "/api/puzzle-set/pz-sample/preview/board.png",
    ],
)
def test_contract_puzzle_set_paths(pathname, contract):
    assert _is_puzzle_set_path(pathname, contract)


@pytest.mark.parametrize(
    "pathname",
    [
        "/ops",
        "/ops/",
        "/api/ops/snapshot",
        "/api/ops/go-online",
    ],
)
def test_contract_ops_paths(pathname, contract):
    assert _is_ops_path(pathname, contract)


@pytest.mark.parametrize(
    "pathname",
    [
        "/ops",
        "/ops/",
        "/api/ops/snapshot",
    ],
)
def test_contract_ops_paths_not_proxied(pathname, contract):
    assert _is_ops_path(pathname, contract)
    assert not _should_proxy_to_origin(pathname, contract)


def test_contract_live_leaderboard_routes_present(contract):
    for route in (
        "/api/leaderboard/live",
        "/api/leaderboard/puzzles/live",
        "/api/leaderboard/identify/live",
    ):
        assert route in contract["proxy_path_exact"]


def test_contract_watch_asset_prefixes_present(contract):
    prefixes = contract["watch_asset_path_prefixes"]
    assert "/g/" in prefixes
    assert "/p/" in prefixes
    assert "/i/" in prefixes


def test_proxy_header_forwarding_node():
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    result = subprocess.run(
        ["node", "--test", str(PROXY_HEADER_TEST)],
        cwd=PROXY_HEADER_TEST.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_per_key_game_limits_independent_across_keys(monkeypatch):
    """Per-key game buckets stay separate regardless of client IP."""
    monkeypatch.setenv("CHESS_HARNESS_TRUSTED_PROXIES", "127.0.0.0/8")
    tight = HarnessLimits(
        max_concurrent_games=10,
        max_engine_processes=12,
        max_games_per_hour_per_key=2,
        max_moves_per_hour_per_key=600,
        idle_timeout_sec=300,
        max_agent_registrations_per_ip_per_hour=10,
    )
    enforcer = ApiLimitEnforcer(tight)
    game_service = GameService(game_manager=GameManager())
    auth_a = AuthContext(model_id="proxy-a", key_fingerprint="fp-proxy-a")
    auth_b = AuthContext(model_id="proxy-b", key_fingerprint="fp-proxy-b")

    for _ in range(2):
        assert enforcer.check_create_game(game_service, auth_a) is None
        enforcer.record_create_game(auth_a)

    assert enforcer.check_create_game(game_service, auth_a) is not None
    assert enforcer.check_create_game(game_service, auth_b) is None


def test_distinct_forwarded_ips_get_separate_registration_buckets(limit_client, monkeypatch):
    """Forwarded visitor IPs through a trusted tunnel hop get independent IP buckets."""
    monkeypatch.setenv("CHESS_HARNESS_TRUSTED_PROXIES", "127.0.0.0/8")
    client, _, _ = limit_client

    for idx, ip in enumerate(("198.51.100.11", "198.51.100.12"), start=1):
        reg = client.post(
            "/api/v1/agents",
            json={"id": f"ip-bucket-{idx}", "name": f"Agent {idx}"},
            headers={"X-Forwarded-For": ip},
        )
        assert reg.status_code == 200, reg.text

    blocked = client.post(
        "/api/v1/agents",
        json={"id": "ip-bucket-3", "name": "Agent 3"},
        headers={"X-Forwarded-For": "198.51.100.11"},
    )
    assert blocked.status_code == 429
