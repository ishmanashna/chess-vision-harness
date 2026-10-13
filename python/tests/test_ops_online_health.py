"""Offline health failures, shared operation status, and safe tunnel control."""
import json
import subprocess
import sys
import time
import urllib.error
from pathlib import Path

import pytest
from fastapi import HTTPException

from chess_harness import ops_health, ops_jobs, ops_online_state


def test_probe_checks_payload_and_bounds_body(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            assert size == 8193
            return b'{"online": false, "ok": true}'
    class Opener:
        def open(self, request, timeout):
            assert timeout == 4
            return Response()
    monkeypatch.setattr(ops_health.urllib.request, "build_opener", lambda *args: Opener())
    assert ops_health.probe("https://example/health")["state"] == "healthy"
    assert ops_health.probe("https://example/api/edge-health", edge=True)["state"] == "unhealthy"


def test_probe_timeout_and_unconfigured(monkeypatch):
    class Opener:
        def open(self, *args, **kwargs): raise TimeoutError("private details")
    monkeypatch.setattr(ops_health.urllib.request, "build_opener", lambda *args: Opener())
    row = ops_health.probe("https://example/health")
    assert row["state"] == "unhealthy" and row["reason"] == "TimeoutError"
    assert row["checked_at"] and row["timeout_seconds"] == 4
    assert ops_health.probe(None)["state"] == "unknown"


def test_saved_files_do_not_prove_health_and_arbitrary_url_is_rejected(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "quick-tunnel.pid").write_text("12345")
    (logs / "quick-tunnel.url").write_text("http://127.0.0.1:9999/private")
    monkeypatch.setattr(ops_health, "tunnel_process", lambda pid: "stale")
    monkeypatch.setattr(ops_health, "probe", lambda url, **kw: {"url": url, "state": "unhealthy" if url else "unknown"})
    row = ops_health.collect(tmp_path, "http://127.0.0.1:8765", "https://example")
    assert row["tunnel"]["state"] == "unknown" and row["tunnel"]["url"] is None
    assert row["process"]["state"] == "stale"


def test_health_refresh_is_single_flight_and_cached(tmp_path, monkeypatch):
    import threading
    release = threading.Event()
    calls = []
    def collect(*args):
        calls.append(1)
        release.wait(2)
        return {"local": {"state": "healthy"}}
    monkeypatch.setattr(ops_health, "collect", collect)
    first = ops_health.health_snapshot(tmp_path, "http://127.0.0.1:8765")
    second = ops_health.health_snapshot(tmp_path, "http://127.0.0.1:8765")
    assert first["stale"] and second["refreshing"]
    release.set()
    for _ in range(100):
        result = ops_health.health_snapshot(tmp_path, "http://127.0.0.1:8765")
        if not result["refreshing"]: break
        time.sleep(.01)
    assert len(calls) == 1 and not result["stale"]
    key = (str(tmp_path), "http://127.0.0.1:8765", result["pages_url"])
    with ops_health._lock:
        ops_health._cache[key] = (result, time.monotonic() - 60)
    assert ops_health.health_snapshot(tmp_path, "http://127.0.0.1:8765")["stale"]


def write_status(root, **values):
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    row = dict(schema_version=1, job_id="desktop-test", source="desktop", status="running", phase="Setting GitHub secret", started_at="2026-10-13T12:00:00Z")
    row.update(values)
    (logs / "go-online-status.json").write_text(json.dumps(row))
    (logs / "go-online-transcript.log").write_text("Retrying GitHub TLS timeout\n")


def test_shared_record_survives_new_job_state_and_detects_interruption(tmp_path):
    write_status(tmp_path)
    with ops_online_state.operation_lock(tmp_path):
        row = ops_jobs.GoOnlineJobState().snapshot(tmp_path)
        assert row["status"] == "running" and row["job_id"] == "desktop-test"
        assert row["source"] == "desktop" and "TLS timeout" in row["log_tail"][-1]
        with pytest.raises(BlockingIOError):
            with ops_online_state.operation_lock(tmp_path): pass
    assert ops_jobs.GoOnlineJobState().snapshot(tmp_path)["status"] == "fail"
    write_status(tmp_path, status="fail", failure_reason="GitHub TLS retries exhausted", exit_code=1)
    assert ops_jobs.GoOnlineJobState().snapshot(tmp_path)["failure_reason"] == "GitHub TLS retries exhausted"


@pytest.mark.parametrize("identity", ["stale", "mismatch", "unknown"])
def test_sleep_never_kills_unverified_pid(tmp_path, monkeypatch, identity):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "quick-tunnel.pid").write_text("42")
    (logs / "quick-tunnel.url").write_text("https://old.trycloudflare.com")
    monkeypatch.setattr(ops_jobs, "_stop_tracked_tunnel", None)
    monkeypatch.setattr(ops_jobs, "tunnel_process", lambda pid: identity)
    monkeypatch.setattr(ops_jobs, "_kill_pid", lambda pid: pytest.fail("Unverified PID must not be killed"))
    if identity == "unknown":
        with pytest.raises(HTTPException): ops_jobs.stop_tracked_quick_tunnel(tmp_path)
        assert (logs / "quick-tunnel.pid").exists()
    else:
        assert not ops_jobs.stop_tracked_quick_tunnel(tmp_path)["stopped"]
        assert not (logs / "quick-tunnel.url").exists()


def test_log_tail_is_bounded(tmp_path):
    log = tmp_path / "log"
    log.write_text("x" * 100000 + "\n" + "\n".join(str(i) for i in range(100)))
    tail = ops_online_state.log_tail(log)
    assert len(tail) == 40 and tail[0] == "60" and tail[-1] == "99"


@pytest.mark.parametrize("succeeds", [False, True])
def test_verified_sleep_retains_tracking_on_stop_failure(tmp_path, monkeypatch, succeeds):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "quick-tunnel.pid").write_text("42")
    (logs / "quick-tunnel.url").write_text("https://old.trycloudflare.com")
    monkeypatch.setattr(ops_jobs, "_stop_tracked_tunnel", None)
    monkeypatch.setattr(ops_jobs, "tunnel_process", lambda pid: "running")
    killed = []
    monkeypatch.setattr(ops_jobs, "_kill_pid", lambda pid: killed.append(pid) or succeeds)
    if succeeds:
        assert ops_jobs.stop_tracked_quick_tunnel(tmp_path)["stopped"]
        assert not (logs / "quick-tunnel.url").exists()
    else:
        with pytest.raises(HTTPException): ops_jobs.stop_tracked_quick_tunnel(tmp_path)
        assert (logs / "quick-tunnel.pid").exists() and (logs / "quick-tunnel.url").exists()
    assert killed == [42]


def test_health_route_is_loopback_only(spectator_client):
    assert spectator_client.get("/api/ops/health", headers={"Host": "example.com"}).status_code == 404


@pytest.mark.skipif(sys.platform != "win32", reason="Desktop uses Windows PowerShell")
def test_powershell_and_python_share_lock_and_record(tmp_path):
    helper = Path(__file__).resolve().parents[2] / "deploy" / "online-operation.ps1"
    # Only exercise the status helper; no server, tunnel, GitHub, or deploy calls.
    quote = lambda value: str(value).replace("'", "''")
    command = f"$ErrorActionPreference = 'Stop'; . '{quote(helper)}'; Open-OnlineOperation -Logs '{quote(tmp_path / 'logs')}' -OperationId 'offline-test'; Set-OnlinePhase 'GitHub retry'; Start-Sleep -Seconds 1; Close-OnlineOperation -Code 1 -Reason 'TLS retries exhausted'"
    proc = subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", command], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = time.monotonic() + 5
    running = None
    while running is None and time.monotonic() < deadline:
        running = ops_online_state.shared_snapshot(tmp_path)
        if running is None: time.sleep(.02)
    assert running["status"] == "running" and running["job_id"] == "offline-test"
    with pytest.raises(HTTPException) as error:
        ops_jobs.GoOnlineJobState().start(base_dir=tmp_path, repo_root=helper.parent.parent)
    assert error.value.status_code == 409
    stdout, stderr = proc.communicate(timeout=5)
    assert proc.returncode == 0, stderr.decode(errors="replace")
    final = ops_jobs.GoOnlineJobState().snapshot(tmp_path)
    assert final["status"] == "fail" and final["failure_reason"] == "TLS retries exhausted"
    with ops_online_state.operation_lock(tmp_path): pass


@pytest.mark.skipif(sys.platform != "win32", reason="Windows desktop launcher")
@pytest.mark.parametrize("fail", [False, True])
def test_launcher_records_success_and_github_failure_offline(tmp_path, fail):
    import shutil
    deploy = Path(__file__).resolve().parents[2] / "deploy"
    for name in ("online-operation.ps1", "github-retry.ps1"):
        shutil.copyfile(deploy / name, tmp_path / name)
    source = (deploy / "go-online.ps1").read_text(encoding="utf-8-sig")
    # Replace external operations at the main boundary. Exercise the real wrapper,
    # phases, transcript, exit handling, and shared status without touching services.
    stubs = '''
function Ensure-Harness { Write-Host 'Offline harness fixture' }
function Resolve-Cloudflared { return 'offline' }
function Start-QuickTunnel {
    Set-Content -LiteralPath $TunnelPidPath -Value '42'
    return 'https://fixture.trycloudflare.com'
}
function Wait-OriginHealth { return $true }
function Invoke-GitHubWithRetry { GITHUB_STUB }
'''.replace("GITHUB_STUB", "throw 'TLS retries exhausted'" if fail else "Write-Host 'Offline GitHub fixture'")
    fixture = tmp_path / "go-online.ps1"
    fixture.write_text(source.replace("# --- main ---", stubs + "\n# --- main ---"), encoding="utf-8-sig")
    import os
    runtime = tmp_path / "runtime"
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(fixture), "-RepoRoot", str(tmp_path), "-NoPanel", "-SkipVerify", "-SkipDeploy"],
                          capture_output=True, timeout=10, env=dict(os.environ, CHESS_HARNESS_DIR=str(runtime)))
    status = ops_online_state.shared_snapshot(runtime)
    assert status["status"] == ("fail" if fail else "ok"), proc.stderr.decode(errors="replace")
    assert bool(proc.returncode) == fail
    if fail: assert status["failure_reason"] == "TLS retries exhausted"
    assert any("Offline harness fixture" in line for line in status["log_tail"])
