"""Phase 9d: calibration worker out of serve process."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]

PYTHON_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PYTHON_ROOT.parent
sys.path.insert(0, str(PYTHON_ROOT / "src"))

from chess_harness.calibration_worker_ipc import (
    calibration_worker_port,
    http_json,
    worker_health_ok,
)
from chess_harness.continuous_calibration import (
    get_continuous_calibration,
    resolve_calibration_manager,
)


@pytest.fixture
def calibration_worker_subprocess(monkeypatch, tmp_path):
    """Spawn a real calibration worker for out-of-process integration."""
    monkeypatch.delenv("CHESS_HARNESS_CALIBRATION_IN_PROCESS", raising=False)
    import chess_harness.continuous_calibration as cc

    cc._manager = None
    cc._remote_manager = None

    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    env = os.environ.copy()
    env["CHESS_HARNESS_DIR"] = str(harness_dir)
    env["CHESS_HARNESS_CALIBRATION_WORKER"] = "1"
    port = calibration_worker_port()
    env["CHESS_HARNESS_CALIBRATION_WORKER_PORT"] = str(port)
    env["CHESS_HARNESS_CALIBRATION_IN_PROCESS"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "chess_harness.calibration_worker"],
        env=env,
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if worker_health_ok(timeout=0.5):
            break
        if proc.poll() is not None:
            pytest.fail("calibration worker exited before becoming healthy")
        time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("calibration worker health timeout")

    yield proc, port, harness_dir
    try:
        http_json("POST", "/shutdown", timeout=3.0)
    except Exception:
        pass
    proc.wait(timeout=10)
    cc._manager = None
    cc._remote_manager = None


def test_resolve_calibration_manager_uses_remote_by_default(monkeypatch, calibration_worker_subprocess):
    proc, _port, _harness_dir = calibration_worker_subprocess
    monkeypatch.delenv("CHESS_HARNESS_CALIBRATION_IN_PROCESS", raising=False)
    import chess_harness.continuous_calibration as cc

    cc._remote_manager = None
    mgr = resolve_calibration_manager()
    from chess_harness.calibration_remote import RemoteContinuousCalibrationManager

    assert isinstance(mgr, RemoteContinuousCalibrationManager)
    payload = mgr.status_payload()
    assert payload.get("pairing_mode") == "floaters"
    assert proc.poll() is None


def test_worker_health_and_status_payload(calibration_worker_subprocess):
    _proc, _port, _harness_dir = calibration_worker_subprocess
    payload = http_json("GET", "/status-payload", timeout=5.0)
    assert payload.get("pairing_mode") == "floaters"
    assert "parallel_hard_cap" in payload
    assert "fleet_parallel_hard_cap" in payload


def test_get_continuous_calibration_stays_local():
    mgr = get_continuous_calibration()
    from chess_harness.continuous_calibration import ContinuousCalibrationManager

    assert isinstance(mgr, ContinuousCalibrationManager)
