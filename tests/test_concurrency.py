"""Concurrency tests for per-game locking."""

import os
import sys
import time
from threading import Thread

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.game_manager import GameBusyError, GameManager


def test_game_lock_blocks_second_acquirer(tmp_path, monkeypatch):
    gm = GameManager(base_dir=str(tmp_path / "chess_harness"))
    monkeypatch.setattr(gm, "LOCK_TIMEOUT", 0.3)

    results: list[str] = []

    def holder():
        with gm.game_lock("lock1"):
            results.append("held")
            time.sleep(0.6)

    def waiter():
        time.sleep(0.1)
        try:
            with gm.game_lock("lock1"):
                results.append("acquired")
        except GameBusyError:
            results.append("busy")

    t1 = Thread(target=holder)
    t2 = Thread(target=waiter)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results[0] == "held"
    assert "busy" in results
