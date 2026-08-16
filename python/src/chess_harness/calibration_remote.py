"""HTTP facade for continuous calibration running in a worker process.

POST mutations (start/stop/pairing) proxy to the worker. Display status on serve reads
the worker ``status.json`` snapshot and on-disk calibration files — not ``/status-payload``
or enrich RPC on every GET.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Set

from .calibration_worker_ipc import calibration_worker_base_url, http_json


class RemoteContinuousCalibrationManager:
    """Proxy ContinuousCalibrationManager API to the calibration worker."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or calibration_worker_base_url()).rstrip("/")

    async def _call(
        self,
        method: str,
        path: str,
        *,
        query: Dict[str, Any] | None = None,
        body: Dict[str, Any] | None = None,
        timeout: float = 120.0,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            http_json,
            method,
            path,
            query=query,
            body=body,
            timeout=timeout,
            base_url=self._base_url,
        )

    def pairing_mode(self) -> str:
        payload = http_json("GET", "/status-payload", base_url=self._base_url, timeout=5.0)
        return str(payload.get("pairing_mode") or "floaters")

    def fixed_opponent_id(self) -> str | None:
        payload = http_json("GET", "/status-payload", base_url=self._base_url, timeout=5.0)
        return payload.get("fixed_opponent_id")

    def set_pairing_mode(self, mode: str) -> str:
        payload = self._sync_post("/pairing-mode", query={"mode": mode})
        return str(payload.get("pairing_mode") or mode)

    def set_fixed_opponent(self, opponent_id: str) -> str:
        payload = self._sync_post("/fixed-opponent", query={"opponent": opponent_id})
        return str(payload.get("fixed_opponent_id") or opponent_id)

    def _sync_post(self, path: str, query: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return http_json("POST", path, query=query, base_url=self._base_url, timeout=30.0)

    def is_running(self, engine_id: str) -> bool:
        return engine_id in self.running_engines()

    def running_engines(self) -> Set[str]:
        payload = http_json("GET", "/status-payload", base_url=self._base_url, timeout=5.0)
        engines = payload.get("continuous_engines") or []
        return set(engines)

    def fleet_parallel_in_use(self) -> int:
        payload = http_json("GET", "/status-payload", base_url=self._base_url, timeout=5.0)
        parallel_by = payload.get("parallel_by_engine") or {}
        return sum(int(v) for v in parallel_by.values())

    def status_payload(self) -> Dict[str, Any]:
        return http_json("GET", "/status-payload", base_url=self._base_url, timeout=10.0)

    async def start(self, engine_id: str, *, parallel: int = 1) -> None:
        await self._call(
            "POST",
            f"/continuous/{engine_id}/start",
            query={"parallel": parallel},
        )

    async def stop(self, engine_id: str) -> None:
        await self._call("POST", f"/continuous/{engine_id}/stop")

    async def start_all(self, *, parallel: int = 1) -> List[str]:
        payload = await self._call(
            "POST",
            "/start-all",
            query={"parallel": parallel, "confirm": True},
        )
        started = payload.get("started")
        if isinstance(started, list):
            return [str(x) for x in started]
        return []

    async def stop_all(self) -> List[str]:
        payload = await self._call("POST", "/stop-all")
        stopped = payload.get("stopped")
        if isinstance(stopped, list):
            return [str(x) for x in stopped]
        return []

    async def stop_running_engines(self) -> List[str]:
        return await self.stop_all()
