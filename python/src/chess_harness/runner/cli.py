"""CLI dispatch for chess-harness runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from ..agent_http.transport import urllib_transport
from .config import load_runner_config
from .loop import run_runner
from .paths import default_config_path
from .probe import run_probe


def _parse_args(args: list[str]) -> tuple[list[str], Optional[Path], bool, int]:
    config_path: Optional[Path] = None
    once = False
    iterations = 1
    rest: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--config" and i + 1 < len(args):
            config_path = Path(args[i + 1])
            i += 2
        elif args[i] == "--once":
            once = True
            i += 1
        elif args[i] == "--iterations" and i + 1 < len(args):
            iterations = max(1, int(args[i + 1]))
            i += 2
        else:
            rest.append(args[i])
            i += 1
    return rest, config_path, once, iterations


def cmd_runner_probe(argv: list[str] | None = None) -> int:
    args = list(sys.argv[2:] if argv is None else argv)
    _rest, config_path, _once, _iters = _parse_args(args)
    path = config_path or default_config_path()
    results = run_probe(config_path=path, transport=urllib_transport())
    print(json.dumps({"ok": True, "config": str(path), "results": results}, indent=2))
    return 0


def cmd_runner(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "runner":
        args = args[1:]
    if args and args[0] == "probe":
        return cmd_runner_probe(args[1:])
    _rest, config_path, once, iterations = _parse_args(args)
    path = config_path or default_config_path()
    load_runner_config(path)
    outcomes = run_runner(
        config_path=path,
        transport=urllib_transport(),
        once=once,
        iterations=iterations,
    )
    print(json.dumps({"ok": True, "config": str(path), "outcomes": outcomes}, indent=2))
    return 0
