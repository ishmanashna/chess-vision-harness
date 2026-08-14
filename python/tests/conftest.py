"""Shared test constants and fixtures."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PYTHON_ROOT.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(PYTHON_ROOT / "src"))

STOCKFISH_BIN = REPO_ROOT / "bin" / "stockfish-windows-x86-64.exe"

os.environ.setdefault("STOCKFISH_PATH", str(STOCKFISH_BIN))
os.environ.setdefault("MODELS_FILE", str(FIXTURES / "models.json"))
os.environ.setdefault("OPPONENTS_FILE", str(REPO_ROOT / "config" / "opponents.json"))

DEFAULT_MODEL = "composer-2.5"

# Opponents in the committed catalog (updated when ladder is pruned)
LOW_OPPONENT = "stockfish-handicap:noise10"
MID_OPPONENT = "stockfish-handicap:noise22"
UNCALIBRATED_OPPONENT = "stockfish-handicap:noise7"

# Fixtures whose tests spawn Stockfish or run full engine integration flows.
_SLOW_FIXTURES = frozenset({"controller", "ctrl", "mcp", "engine", "stockfish_engine"})

# Modules that are entirely Stockfish-backed or subprocess smokes.
_SLOW_MODULES = frozenset(
    {
        "test_idle",
        "test_fen",
        "test_ambiguous",
        "test_pgn",
        "test_mcp",
        "test_benchmark_opponents",
        "test_imagine",
        "test_human_vs_agent",
    }
)

# Individual tests marked slow even without the fixtures above.
_SLOW_TEST_NAMES = frozenset(
    {
        "test_api_v1_full_game_flow",
        "test_api_v1_board_text_fallback_is_live_and_authenticated",
        "test_live_stockfish_shallow",
        "test_create_game_via_api_v1",
    }
)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: integration tests that may touch Stockfish or the full HTTP stack",
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        module = item.module.__name__.split(".")[-1] if item.module else ""
        if module in _SLOW_MODULES:
            item.add_marker(pytest.mark.slow)
            item.add_marker(pytest.mark.integration)
            continue
        if item.name in _SLOW_TEST_NAMES:
            item.add_marker(pytest.mark.slow)
            item.add_marker(pytest.mark.integration)
            continue
        if _SLOW_FIXTURES.intersection(item.fixturenames):
            item.add_marker(pytest.mark.slow)
            item.add_marker(pytest.mark.integration)


@pytest.fixture
def stockfish_available():
    """Skip when no Stockfish binary is available (local dev without engines)."""
    path = os.environ.get("STOCKFISH_PATH", str(STOCKFISH_BIN))
    if not Path(path).is_file():
        pytest.skip("Stockfish binary not available")


@pytest.fixture(scope="module")
def stockfish_engine(stockfish_available):
    from chess_harness.engine import StockfishAdapter

    engine = StockfishAdapter()
    yield engine
    engine.quit()


@pytest.fixture
def temp_dir():
    """Temporary directory removed after the test."""
    directory = tempfile.mkdtemp()
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def game_manager(temp_dir):
    from chess_harness.game_manager import GameManager

    return GameManager(base_dir=temp_dir)


@pytest.fixture
def controller(game_manager):
    """BoardController with real opponent engines; auto-marked slow."""
    from chess_harness.board_controller import BoardController

    ctrl = BoardController(game_manager)
    yield ctrl
    ctrl.opponent_mgr.release()
    if ctrl._eval_engine is not None:
        ctrl._eval_engine.quit()
        ctrl._eval_engine = None


@pytest.fixture
def ctrl(tmp_path):
    """Alias used by older board-controller tests."""
    from chess_harness.board_controller import BoardController
    from chess_harness.game_manager import GameManager

    gm = GameManager(base_dir=str(tmp_path / "chess_harness"))
    c = BoardController(gm)
    yield c
    c.opponent_mgr.release()
    if c._eval_engine is not None:
        c._eval_engine.quit()
        c._eval_engine = None


@pytest.fixture
def harness_client(tmp_path, monkeypatch):
    """Isolated spectator FastAPI client backed by a temp harness dir."""
    from harness_client import configure_spectator_harness, make_test_client, teardown_spectator_harness

    harness_dir = configure_spectator_harness(tmp_path / "harness", monkeypatch)
    client = make_test_client()
    yield client, harness_dir
    teardown_spectator_harness()


@pytest.fixture
def api_client(harness_client):
    """Backward-compatible alias for /api/v1 integration tests."""
    return harness_client


@pytest.fixture
def create_client(harness_client):
    """Backward-compatible alias for create-game shell tests."""
    return harness_client


@pytest.fixture
def list_client(harness_client):
    """Backward-compatible alias for spectator list tests."""
    return harness_client


@pytest.fixture
def spectator_client(harness_client):
    """Single TestClient for security/UI tests that do not need harness_dir."""
    client, _harness_dir = harness_client
    return client


@pytest.fixture(autouse=True)
def calibration_in_process_for_tests(monkeypatch):
    """Keep calibration in-process for the test suite (worker isolation has its own test)."""
    monkeypatch.setenv("CHESS_HARNESS_CALIBRATION_IN_PROCESS", "1")
    import chess_harness.continuous_calibration as cc

    cc._manager = None
    cc._remote_manager = None
    yield
    cc._manager = None
    cc._remote_manager = None


@pytest.fixture(autouse=True)
def restore_models_fixture():
    path = FIXTURES / "models.json"
    original = path.read_bytes()
    yield
    path.write_bytes(original)


@pytest.fixture(autouse=True)
def isolate_shipped_data(tmp_path, monkeypatch):
    """Redirect snapshot and calibration writes into tmp_path.

    Prevents the test suite from ever touching ``public-site/data/`` or
    ``elo_calibration/results/`` — the two directories that ship to production.
    """
    snap_out = tmp_path / "leaderboard.json"
    puzzle_out = tmp_path / "puzzles_leaderboard.json"
    finished_db = tmp_path / "finished_games.sqlite"
    monkeypatch.setenv("CHESS_HARNESS_FINISHED_DB", str(finished_db))
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.default_output_path",
        lambda: snap_out,
    )
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.default_puzzle_leaderboard_path",
        lambda: puzzle_out,
    )
    cal_results = tmp_path / "elo_calibration" / "results"
    cal_results.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "chess_harness.calibration_view._results_root",
        lambda: cal_results,
    )
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard.request_public_snapshots_refresh",
        lambda: None,
    )
    monkeypatch.setattr(
        "chess_harness.snapshot_leaderboard._inject_inline_snapshot",
        lambda _json: None,
    )
