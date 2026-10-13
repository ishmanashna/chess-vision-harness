import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chess_harness import ops_restart as api, restart_worker as worker

LOCAL = {"Host": "127.0.0.1:8765"}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "resolve_base_dir", lambda: tmp_path)
    monkeypatch.setattr(api, "active_work", lambda root: [])
    import chess_harness.ops_jobs as jobs
    monkeypatch.setattr(jobs, "_go_online_job", SimpleNamespace(status="idle"))
    app = FastAPI()
    api.register_restart_routes(app)
    called = []
    app.state.request_server_shutdown = lambda: called.append(True)
    return TestClient(app), app, tmp_path, called


def test_handoff_acknowledged_before_shutdown_and_blocks_writes(setup, monkeypatch):
    client, app, root, called = setup
    real_write = api.write_status
    def write(root, row):
        real_write(root, dict(row, phase="Handoff ready") if row.get("helper_pid") else row)
    monkeypatch.setattr(api, "write_status", write)
    def spawn(*args):
        assert not called
        return SimpleNamespace(pid=123, poll=lambda: None)
    monkeypatch.setattr(api, "spawn_handoff", spawn)
    response = client.post("/api/ops/restart-server", headers=LOCAL)
    assert response.status_code == 202
    assert called == [True]
    assert client.post("/anything", headers=LOCAL).status_code == 409
    assert client.get("/api/ops/restart-server", headers=LOCAL).json()["supported"]


@pytest.mark.parametrize("mode,code", [("public",404),("unmanaged",409),("busy",409),("spawn",500),("helper_exit",500)])
def test_rejected_restart_keeps_server_running(setup, monkeypatch, mode, code):
    client, app, root, called = setup
    headers = LOCAL
    if mode == "public": headers = {"Host": "example.com"}
    if mode == "unmanaged": app.state.request_server_shutdown = None
    if mode == "busy": monkeypatch.setattr(api,"active_work",lambda root:["games are running"])
    def spawn(*args):
        if mode == "helper_exit": return SimpleNamespace(pid=123,poll=lambda:1)
        raise OSError("test failure")
    monkeypatch.setattr(api,"spawn_handoff",spawn)
    assert client.post("/api/ops/restart-server",headers=headers).status_code == code
    assert not called
    assert not app.state.restart_pending


def test_restart_worker_never_stops_occupied_port(tmp_path, monkeypatch):
    api.write_status(tmp_path,{"operation_id":"test","old_pid":100})
    monkeypatch.setattr(worker,"parent_alive",lambda pid:False)
    monkeypatch.setattr(worker,"is_port_in_use",lambda host,port:True)
    monkeypatch.setattr(worker.subprocess,"Popen",lambda *a,**kw:pytest.fail("must not launch"))
    worker.restart(tmp_path,"test","127.0.0.1",8765,100)
    row = api.read_status(tmp_path)
    assert row["status"] == "fail" and "occupied" in row["phase"]


def test_cross_site_page_cannot_restart_localhost(setup):
    client, app, root, called = setup
    assert client.post("/api/ops/restart-server", headers=dict(LOCAL,Origin="https://example.com")).status_code == 404
    assert not called


def test_restart_worker_requires_matching_new_pid_and_health(tmp_path, monkeypatch):
    api.write_status(tmp_path,{"operation_id":"test","old_pid":100})
    monkeypatch.setattr(worker,"parent_alive",lambda pid:False)
    monkeypatch.setattr(worker,"is_port_in_use",lambda host,port:False)
    monkeypatch.setattr(worker,"healthy",lambda *a:True)
    def spawn(command, **kwargs):
        assert "--force" not in command
        assert kwargs["env"]["CHESS_HARNESS_RESTART_HANDOFF"] == "1"
        (tmp_path/'spectator.json').write_text(json.dumps({"pid":123}))
        return SimpleNamespace(pid=123,poll=lambda:None)
    monkeypatch.setattr(worker.subprocess,"Popen",spawn)
    worker.restart(tmp_path,"test","127.0.0.1",8765,100)
    assert api.read_status(tmp_path)["status"] == "ready"
