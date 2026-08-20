"""Per-slot provider rpm/rpd tracking."""

from __future__ import annotations

import time
from collections import deque
from typing import Deque


class QuotaTracker:
    """Sliding-window counters for provider calls (not harness API)."""

    def __init__(self, *, rpm: int, rpd: int):
        self.rpm = max(1, rpm)
        self.rpd = max(1, rpd)
        self._minute: Deque[float] = deque()
        self._day: Deque[float] = deque()
        self.exhausted = False

    def _prune(self, now: float) -> None:
        while self._minute and now - self._minute[0] >= 60.0:
            self._minute.popleft()
        while self._day and now - self._day[0] >= 86400.0:
            self._day.popleft()

    def allow(self) -> bool:
        if self.exhausted:
            return False
        now = time.time()
        self._prune(now)
        return len(self._minute) < self.rpm and len(self._day) < self.rpd

    def record(self) -> None:
        now = time.time()
        self._prune(now)
        self._minute.append(now)
        self._day.append(now)
        if len(self._minute) >= self.rpm or len(self._day) >= self.rpd:
            self.exhausted = True

    def stop(self, reason: str = "quota") -> str:
        self.exhausted = True
        return reason
