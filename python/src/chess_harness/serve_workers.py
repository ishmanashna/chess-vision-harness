"""Bounded thread pool for blocking serve hot-path work."""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_executor: ThreadPoolExecutor | None = None
_eval_sem: asyncio.Semaphore | None = None


def _pool_size() -> int:
    raw = os.environ.get("CHESS_HARNESS_SERVE_WORKERS")
    if raw:
        try:
            return max(2, min(32, int(raw)))
        except ValueError:
            pass
    cpu = os.cpu_count() or 4
    return max(4, min(16, cpu * 2))


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=_pool_size(),
            thread_name_prefix="chess-serve",
        )
    return _executor


def eval_semaphore() -> asyncio.Semaphore:
    global _eval_sem
    if _eval_sem is None:
        from .limits import load_limits

        lim = load_limits()
        slots = max(1, min(8, lim.max_engine_processes // 2))
        _eval_sem = asyncio.Semaphore(slots)
    return _eval_sem


async def run_blocking(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    loop = asyncio.get_running_loop()
    if kwargs:
        return await loop.run_in_executor(
            get_executor(), lambda: fn(*args, **kwargs)
        )
    return await loop.run_in_executor(get_executor(), fn, *args)


async def run_eval(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    async with eval_semaphore():
        return await run_blocking(fn, *args, **kwargs)


def shutdown_workers() -> None:
    global _executor, _eval_sem
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None
    _eval_sem = None
