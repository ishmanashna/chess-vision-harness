"""Runner scheduler — reconcile, resume, create."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from ..agent_http import AgentHttpClient
from ..agent_http.queue import default_queue_path
from .activation import slot_is_active
from .adapters import build_adapter
from .config import RunnerConfig, SlotConfig, load_runner_config
from .keys import ensure_harness_key, keys_path
from .log import RunnerLog, log_path
from .probe_state import load_probe_status
from .quota import QuotaTracker
from .slot_worker import play_game
from .slot_worker_identify import play_identify_attempt
from .slot_worker_puzzles import play_puzzle_attempt

TransportFn = Any


class SlotRunner:
    def __init__(
        self,
        config: RunnerConfig,
        *,
        transport: TransportFn,
        harness_dir: Optional[Path] = None,
        logger: Optional[RunnerLog] = None,
        stub_moves=None,
        max_agent_plies: Optional[int] = None,
    ):
        self.config = config
        self.transport = transport
        self.harness_dir = harness_dir
        self.logger = logger or RunnerLog(log_path(harness_dir))
        self.stub_moves = stub_moves
        self.max_agent_plies = max_agent_plies
        self._clients: Dict[str, AgentHttpClient] = {}
        self._quotas: Dict[str, QuotaTracker] = {}
        self.probe_status = load_probe_status(
            Path(harness_dir) / "runner" / "probe_status.json" if harness_dir else None
        )

    def _queue_path(self) -> Path:
        return default_queue_path(self.harness_dir)

    def _keys_file(self) -> Path:
        return keys_path(self.harness_dir)

    def _client_for(self, slot: SlotConfig) -> AgentHttpClient:
        cached = self._clients.get(slot.inscribed_id)
        if cached is not None:
            return cached
        api_key = ensure_harness_key(
            base_url=self.config.harness_base_url,
            inscribed_id=slot.inscribed_id,
            observation=slot.observation,
            transport=self.transport,
            path=self._keys_file(),
        )
        client = AgentHttpClient(
            self.config.harness_base_url,
            api_key,
            model_id=slot.inscribed_id,
            transport=self.transport,
            queue_path=self._queue_path(),
        )
        self._clients[slot.inscribed_id] = client
        return client

    def _quota_for(self, slot: SlotConfig) -> QuotaTracker:
        if slot.inscribed_id not in self._quotas:
            self._quotas[slot.inscribed_id] = QuotaTracker(rpm=slot.rpm, rpd=slot.rpd)
        return self._quotas[slot.inscribed_id]

    def active_slots(self) -> List[SlotConfig]:
        return [slot for slot in self.config.slots if slot_is_active(slot, self.probe_status)]

    def reconcile_all(self) -> None:
        for slot in self.active_slots():
            self._client_for(slot).reconcile_queue()

    def _run_slot(self, slot: SlotConfig, quota: QuotaTracker, client: AgentHttpClient, adapter) -> Dict[str, Any]:
        kind = slot.kind
        if kind == "puzzles":
            return play_puzzle_attempt(client, adapter, slot, quota, self.logger)
        if kind == "identify":
            return play_identify_attempt(client, adapter, slot, quota, self.logger)
        return play_game(
            client,
            adapter,
            slot,
            quota,
            self.logger,
            max_agent_plies=self.max_agent_plies,
        )

    def run_once(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        active = self.active_slots()
        if not active:
            self.logger.write("runner_idle", error="no_active_slots")
            return results

        self.reconcile_all()
        live_count = 0
        for slot in active:
            if live_count >= self.config.max_concurrent_games:
                break
            quota = self._quota_for(slot)
            if quota.exhausted:
                results.append({"slot": slot.inscribed_id, "ok": False, "reason": "quota"})
                continue
            client = self._client_for(slot)
            adapter = build_adapter(slot, self.transport, stub_moves=self.stub_moves)

            if slot.kind == "ave":
                resumed = False
                for entry in client.load_queue():
                    if entry.model_id != slot.inscribed_id:
                        continue
                    live_count += 1
                    resumed = True
                    outcome = play_game(
                        client,
                        adapter,
                        slot,
                        quota,
                        self.logger,
                        game_id=entry.game_id,
                        max_agent_plies=self.max_agent_plies,
                    )
                    results.append({"slot": slot.inscribed_id, **outcome})
                    break
                if resumed:
                    continue

            if live_count >= self.config.max_concurrent_games:
                break
            outcome = self._run_slot(slot, quota, client, adapter)
            if outcome.get("game_id") or outcome.get("attempt_id"):
                live_count += 1
            results.append({"slot": slot.inscribed_id, **outcome})
        return results


def run_runner(
    *,
    config_path: Path | None = None,
    transport: TransportFn,
    harness_dir: Path | None = None,
    once: bool = False,
    iterations: int = 1,
    stub_moves=None,
    max_agent_plies: Optional[int] = None,
) -> List[Dict[str, Any]]:
    config = load_runner_config(config_path)
    runner = SlotRunner(
        config,
        transport=transport,
        harness_dir=harness_dir,
        stub_moves=stub_moves,
        max_agent_plies=max_agent_plies,
    )
    all_results: List[Dict[str, Any]] = []
    count = iterations if once else iterations
    for _ in range(max(1, count)):
        all_results.extend(runner.run_once())
        if once:
            break
    return all_results
