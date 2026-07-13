"""Smoke test for opponent speed benchmark script."""

import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_benchmark_random_opponent_smoke():
    result = subprocess.run(
        [
            sys.executable,
            os.path.join(ROOT, "scripts", "benchmark_opponents.py"),
            "--only",
            "random",
            "--moves",
            "3",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert "random" in result.stdout
