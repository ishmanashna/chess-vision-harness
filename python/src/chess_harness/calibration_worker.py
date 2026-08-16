"""Dedicated process for continuous calibration engine games."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List

import uvicorn
from fastapi import FastAPI, HTTPException, Query

from .calibration_worker_ipc import calibration_worker_port, calibration_worker_status_path
from .continuous_calibration import (
    assess_fleet_parallel,
    assess_parallel_start,
    assess_start_all,
    can_continuously_calibrate,
    get_continuous_calibration,
)
from .paths import resolve_calibration_worker_dir


def _write_status_snapshot(payload: Dict[str, Any]) -> None:
    path = calibration_worker_status_path()
    resolve_calibration_worker_dir().mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@asynccontextmanager
async def _worker_lifespan(_app: FastAPI):
    try:
        _write_status_snapshot(get_continuous_calibration().status_payload())
    except Exception:
        pass

    async def _status_writer() -> None:
        while True:
            try:
                mgr = get_continuous_calibration()
                _write_status_snapshot(mgr.status_payload())
            except Exception:
                pass
            await asyncio.sleep(1.0)

    task = asyncio.create_task(_status_writer())
    yield
    task.cancel()
    try:
        await get_continuous_calibration().stop_all()
    except Exception:
        pass


worker_app = FastAPI(title="Chess Harness Calibration Worker", lifespan=_worker_lifespan)


@worker_app.get("/health")
async def worker_health():
    return {"ok": True, "service": "calibration-worker"}


@worker_app.get("/status-payload")
async def worker_status_payload():
    return get_continuous_calibration().status_payload()


@worker_app.post("/continuous/{engine_id}/start")
async def worker_start(
    engine_id: str,
    parallel: int = Query(1, ge=1, le=100),
    confirm: bool = Query(False),
):
    mgr = get_continuous_calibration()
    if not can_continuously_calibrate(engine_id, pairing_mode=mgr.pairing_mode()):
        raise HTTPException(400, f"Engine cannot be continuously calibrated: {engine_id}")
    if mgr.is_running(engine_id):
        raise HTTPException(409, f"Continuous calibration already running for {engine_id}")
    err = assess_parallel_start(parallel, confirm=confirm)
    if err:
        raise HTTPException(400, err)
    err = assess_fleet_parallel(mgr, parallel, confirm=confirm)
    if err:
        raise HTTPException(400, err)
    try:
        await mgr.start(engine_id, parallel=parallel)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        if "already running" in str(exc).lower():
            raise HTTPException(409, str(exc)) from exc
        raise
    return {"ok": True, "engine_id": engine_id, "running": True, "parallel": parallel}


@worker_app.post("/continuous/{engine_id}/stop")
async def worker_stop(engine_id: str):
    await get_continuous_calibration().stop(engine_id)
    return {"ok": True, "engine_id": engine_id, "running": False}


@worker_app.post("/pairing-mode")
async def worker_pairing_mode(mode: str = Query(...)):
    mgr = get_continuous_calibration()
    if mgr.running_engines():
        raise HTTPException(
            409,
            "Stop continuous calibration before changing pairing settings",
        )
    try:
        pairing_mode = mgr.set_pairing_mode(mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "pairing_mode": pairing_mode}


@worker_app.post("/fixed-opponent")
async def worker_fixed_opponent(opponent: str = Query(...)):
    mgr = get_continuous_calibration()
    if mgr.running_engines():
        raise HTTPException(
            409,
            "Stop continuous calibration before changing pairing settings",
        )
    try:
        opponent_id = mgr.set_fixed_opponent(opponent)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "fixed_opponent_id": opponent_id}


@worker_app.post("/start-all")
async def worker_start_all(
    parallel: int = Query(1, ge=1, le=100),
    confirm: bool = Query(False),
):
    mgr = get_continuous_calibration()
    err = assess_start_all(mgr, parallel, confirm=confirm)
    if err:
        raise HTTPException(400, err)
    started = await mgr.start_all(parallel=parallel)
    return {"ok": True, "started": started, "count": len(started), "parallel": parallel}


@worker_app.post("/stop-all")
async def worker_stop_all():
    stopped = await get_continuous_calibration().stop_all()
    return {"ok": True, "stopped": stopped, "count": len(stopped)}


@worker_app.post("/shutdown")
async def worker_shutdown():
    await get_continuous_calibration().stop_all()
    loop = asyncio.get_running_loop()
    loop.call_later(0.2, lambda: os._exit(0))
    return {"ok": True, "shutting_down": True}


def run_calibration_worker(host: str = "127.0.0.1", port: int | None = None) -> None:
    bind_port = port or calibration_worker_port()
    print(f"Calibration worker on http://{host}:{bind_port}")
    uvicorn.run(worker_app, host=host, port=bind_port, log_level="info")


if __name__ == "__main__":
    run_calibration_worker()
