"""Operator panel Phase 3: Go Online job runner and sleep-public."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

import chess_harness.ops_jobs as ops_jobs

LOOPBACK_HEADERS = {"Host": "127.0.0.1:8765"}
PUBLIC = {"Host": "example.com"}


@pytest.fixture(autouse=True)
def reset_go_online_job():
    ops_jobs._go_online_job = ops_jobs.GoOnlineJobState()
    ops_jobs._spawn_go_online = None
    ops_jobs._stop_tracked_tunnel = None
    yield
    ops_jobs._go_online_job = ops_jobs.GoOnlineJobState()
    ops_jobs._spawn_go_online = None
    ops_jobs._stop_tracked_tunnel = None


def _slow_fake_spawn(_repo_root: Path, log_path: Path) -> subprocess.Popen:
    log_file = str(log_path)
    script = (
        "import time\n"
        f"log = open({log_file!r}, 'a', encoding='utf-8')\n"
        "log.write('fake: tunnel starting\\n')\n"
        "log.flush()\n"
        "time.sleep(0.35)\n"
        "log.write('fake: public online ready\\n')\n"
        "log.flush()\n"
        "log.close()\n"
    )
    return subprocess.Popen([sys.executable, "-c", script])


def test_go_online_post_starts_job_and_get_reports_ok(spectator_client, monkeypatch):
    client = spectator_client
    monkeypatch.setattr(ops_jobs, "_spawn_go_online", _slow_fake_spawn)

    post = client.post("/api/ops/go-online", headers=LOOPBACK_HEADERS)
    assert post.status_code == 200
    body = post.json()
    assert body["ok"] is True
    assert body["status"] == "running"
    assert body["job_id"]

    running = client.get("/api/ops/go-online", headers=LOOPBACK_HEADERS).json()
    assert running["status"] == "running"
    assert running["job_id"] == body["job_id"]

    deadline = time.monotonic() + 5.0
    final = running
    while time.monotonic() < deadline:
        final = client.get("/api/ops/go-online", headers=LOOPBACK_HEADERS).json()
        if final["status"] in ("ok", "fail"):
            break
        time.sleep(0.05)

    assert final["status"] == "ok"
    assert final["exit_code"] == 0
    assert any("public online ready" in line for line in final["log_tail"])


def test_go_online_second_post_rejected_while_running(spectator_client, monkeypatch):
    client = spectator_client

    def _very_slow_spawn(_repo_root: Path, log_path: Path) -> subprocess.Popen:
        log_file = str(log_path)
        script = (
            "import time\n"
            f"log = open({log_file!r}, 'a', encoding='utf-8')\n"
            "log.write('still running\\n')\n"
            "log.flush()\n"
            "time.sleep(2)\n"
            "log.close()\n"
        )
        return subprocess.Popen([sys.executable, "-c", script])

    monkeypatch.setattr(ops_jobs, "_spawn_go_online", _very_slow_spawn)

    first = client.post("/api/ops/go-online", headers=LOOPBACK_HEADERS)
    assert first.status_code == 200

    second = client.post("/api/ops/go-online", headers=LOOPBACK_HEADERS)
    assert second.status_code == 409

    status = client.get("/api/ops/go-online", headers=LOOPBACK_HEADERS).json()
    assert status["status"] == "running"
    assert status["job_id"] == first.json()["job_id"]


def test_go_online_off_loopback_404(spectator_client):
    client = spectator_client
    assert client.post("/api/ops/go-online").status_code == 404
    assert client.post("/api/ops/go-online", headers=PUBLIC).status_code == 404
    assert client.get("/api/ops/go-online").status_code == 404
    assert client.get("/api/ops/go-online", headers=PUBLIC).status_code == 404


def test_sleep_public_off_loopback_404(spectator_client):
    client = spectator_client
    assert client.post("/api/ops/sleep-public").status_code == 404
    assert client.post("/api/ops/sleep-public", headers=PUBLIC).status_code == 404


def test_sleep_public_stops_tunnel_serve_stays_up(spectator_client, harness_client, monkeypatch):
    spectator = spectator_client
    client, harness_dir = harness_client
    stopped: list[int | None] = []

    def fake_stop(base_dir=None):
        pid_path = (base_dir or harness_dir) / "logs" / "quick-tunnel.pid"
        pid = None
        if pid_path.is_file():
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        stopped.append(pid)
        pid_path.unlink(missing_ok=True)
        return {"ok": True, "stopped": True, "pid": pid}

    monkeypatch.setattr(ops_jobs, "_stop_tracked_tunnel", fake_stop)

    sleeper = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    logs = harness_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "quick-tunnel.pid").write_text(str(sleeper.pid), encoding="ascii")

    resp = client.post("/api/ops/sleep-public", headers=LOOPBACK_HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["stopped"] is True
    assert body["pid"] == sleeper.pid
    assert stopped == [sleeper.pid]
    assert not (logs / "quick-tunnel.pid").exists()

    assert client.get("/health").status_code == 200
    assert client.get("/ops/", headers=LOOPBACK_HEADERS).status_code == 200
    assert spectator.get("/api/ops/snapshot", headers=LOOPBACK_HEADERS).status_code == 200

    sleeper.terminate()
    sleeper.wait(timeout=5)


def test_go_online_script_skips_recycle_when_health_ok():
    text = Path(__file__).resolve().parents[2].joinpath("deploy", "go-online.ps1").read_text(
        encoding="utf-8"
    )
    start = text.index("function Ensure-Harness")
    end = text.index("function Stop-TrackedQuickTunnel")
    block = text[start:end]
    assert "Test-LocalHealth -BaseUrl $BaseUrl" in block
    assert "leaving serve running" in block
    assert "Stop-ManualHarness" not in block
    assert "Set-HarnessBriefEnv -Pages $PagesUrl" in block
    unhealthy = block.split("Test-LocalHealth -BaseUrl $BaseUrl", 1)[1]
    assert "Start-ManualHarness" in unhealthy
