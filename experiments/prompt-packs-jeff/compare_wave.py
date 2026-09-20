#!/usr/bin/env python3
"""Jeff J1–J5 compare wave: 5 packs x 5 games, fixed opponent slate.

Default is dry-run. Pass --go to play (burns TypeSafe API).

Slate (identical for every pack, fixed order) — CALIBRATED ladder Elo only:
  1-3: stockfish-handicap:noise90  (~409; near Jeff inscribed ~402)
  4-5: stockfish-handicap:noise94  (~359)
Never trust config/opponents.json catalog elo (depth4 catalog 200 = ladder 1431).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SRC = REPO / "python" / "src"
sys.path.insert(0, str(SRC))
os.chdir(REPO)

DEFAULT_PACKS = ["j1", "j2", "j3", "j4", "j5"]
OPP_A = "stockfish-handicap:noise90"
OPP_B = "stockfish-handicap:noise94"
OPP_B_FALLBACK = "stockfish-handicap:noise96"
TAG = "jeff-ab-compare"
RUNS = HERE / "runs"
KEY_FILE = Path(r"C:\Users\jordi\Desktop\coding stuff\keys\typesafe_api_key.txt")
MODEL = "jev-latest"
HARNESS = "http://127.0.0.1:8765"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_typesafe_env() -> None:
    if os.environ.get("TYPESAFE_API_KEY", "").strip():
        return
    if KEY_FILE.is_file():
        os.environ["TYPESAFE_API_KEY"] = KEY_FILE.read_text(encoding="utf-8").strip()
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        raise SystemExit(f"Missing TYPESAFE_API_KEY (expected {KEY_FILE})")


def resolve_slate(opp_a: Optional[str] = None, opp_b: Optional[str] = None) -> List[str]:
    from chess_harness.paths import project_root

    opp_path = project_root() / "config" / "opponents.json"
    ids = {
        o["id"]
        for o in json.loads(opp_path.read_text(encoding="utf-8")).get("opponents", [])
    }
    a = opp_a or OPP_A
    b = opp_b or (OPP_B if OPP_B in ids else OPP_B_FALLBACK)
    if a not in ids:
        raise SystemExit(f"Opponent {a} missing from catalog")
    if b not in ids:
        raise SystemExit(f"Opponent B {b} missing from catalog")
    return [a, a, a, b, b]


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_slot(pack_id: str, opponent: str):
    from chess_harness.runner.config import SlotConfig

    return SlotConfig(
        inscribed_id=MODEL,
        provider="typesafe",
        observation="text",
        provider_model=MODEL,
        base_url="https://api.typesafe.ai/v1",
        env_key="TYPESAFE_API_KEY",
        rpm=60,
        rpd=5000,
        kind="ave",
        opponent=opponent,
        agent_color="white",
        prompt_pack=pack_id,
    )


def make_client(slot):
    from chess_harness.agent_http.client import AgentHttpClient
    from chess_harness.agent_http.transport import urllib_transport
    from chess_harness.runner.keys import ensure_harness_key
    from chess_harness.runner.paths import keys_path

    transport = urllib_transport()
    api_key = ensure_harness_key(
        base_url=HARNESS,
        inscribed_id=slot.inscribed_id,
        observation=slot.observation,
        transport=transport,
        path=keys_path(),
    )
    client = AgentHttpClient(
        HARNESS,
        api_key,
        model_id=slot.inscribed_id,
        transport=transport,
    )
    return client, transport


def play_one(
    *,
    pack_id: str,
    opponent: str,
    game_index: int,
    run_id: str,
    jsonl: Path,
    max_agent_plies: Optional[int],
) -> Dict[str, Any]:
    from chess_harness.runner.adapters import build_adapter_for_pack
    from chess_harness.runner.log import RunnerLog
    from chess_harness.runner.quota import QuotaTracker
    from chess_harness.runner.slot_worker import play_game

    slot = make_slot(pack_id, opponent)
    client, transport = make_client(slot)
    adapter = build_adapter_for_pack(slot, transport, pack_id)
    quota = QuotaTracker(rpm=slot.rpm, rpd=slot.rpd)
    logger = RunnerLog(RUNS / run_id / f"{pack_id}-{game_index}.log")
    t0 = time.time()
    append_jsonl(
        jsonl,
        {
            "ts": utc_now(),
            "event": "game_start",
            "run_id": run_id,
            "tag": TAG,
            "pack": pack_id,
            "opponent": opponent,
            "game_index": game_index,
        },
    )
    try:
        kwargs: Dict[str, Any] = {}
        if max_agent_plies is not None:
            kwargs["max_agent_plies"] = max_agent_plies
        outcome = play_game(client, adapter, slot, quota, logger, **kwargs)
        row: Dict[str, Any] = {
            "ts": utc_now(),
            "event": "game_done",
            "run_id": run_id,
            "tag": TAG,
            "pack": pack_id,
            "opponent": opponent,
            "game_index": game_index,
            "elapsed_sec": round(time.time() - t0, 2),
        }
        if isinstance(outcome, dict):
            row.update(outcome)
    except Exception as exc:
        row = {
            "ts": utc_now(),
            "event": "game_error",
            "run_id": run_id,
            "tag": TAG,
            "pack": pack_id,
            "opponent": opponent,
            "game_index": game_index,
            "error": str(exc),
            "traceback": traceback.format_exc()[-2000:],
        }
    append_jsonl(jsonl, row)
    return row


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Jeff J1–J5 compare wave (5x5)")
    ap.add_argument("--go", action="store_true", help="Actually play (default: dry-run)")
    ap.add_argument("--parallel", type=int, default=1, choices=[1, 2])
    ap.add_argument("--max-agent-plies", type=int, default=None)
    ap.add_argument("--packs", default=",".join(DEFAULT_PACKS))
    ap.add_argument("--opp-a", default=None, help="Opponent for games 1-3 (catalog id)")
    ap.add_argument("--opp-b", default=None, help="Opponent for games 4-5 (catalog id)")
    args = ap.parse_args(argv)

    packs = [p.strip() for p in args.packs.split(",") if p.strip()]
    slate = resolve_slate(args.opp_a, args.opp_b)
    jobs = [
        {"pack": pack, "opponent": opp, "game_index": i}
        for pack in packs
        for i, opp in enumerate(slate, start=1)
    ]

    print("=== Jeff A/B compare wave PLAN ===")
    print(f"model:     {MODEL}")
    print(f"harness:   {HARNESS}")
    print(f"tag:       {TAG}")
    print(f"packs ({len(packs)}): {', '.join(packs)}")
    print(f"slate (5): {' | '.join(slate)}")
    print(f"total:     {len(jobs)} games")
    for i, opp in enumerate(slate, 1):
        print(f"  {i}. {opp}")
    if not args.go:
        print("\n[dry-run] Refusing to play without --go.")
        print("  python experiments/prompt-packs-jeff/compare_wave.py --go")
        return 0

    ensure_typesafe_env()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    jsonl = RUNS / f"{run_id}.jsonl"
    (RUNS / run_id).mkdir(parents=True, exist_ok=True)
    append_jsonl(
        jsonl,
        {
            "ts": utc_now(),
            "event": "wave_start",
            "run_id": run_id,
            "tag": TAG,
            "packs": packs,
            "slate": slate,
            "parallel": args.parallel,
        },
    )
    print(f"run_id={run_id}\njsonl={jsonl}")

    results: List[Dict[str, Any]] = []
    if args.parallel <= 1:
        for job in jobs:
            print(f">> {job['pack']} #{job['game_index']} vs {job['opponent']}")
            row = play_one(
                pack_id=job["pack"],
                opponent=job["opponent"],
                game_index=job["game_index"],
                run_id=run_id,
                jsonl=jsonl,
                max_agent_plies=args.max_agent_plies,
            )
            results.append(row)
            print(
                f"<< {row.get('event')} game_id={row.get('game_id')} "
                f"result={row.get('result')}"
            )
    else:
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            futs = {
                pool.submit(
                    play_one,
                    pack_id=job["pack"],
                    opponent=job["opponent"],
                    game_index=job["game_index"],
                    run_id=run_id,
                    jsonl=jsonl,
                    max_agent_plies=args.max_agent_plies,
                ): job
                for job in jobs
            }
            for fut in as_completed(futs):
                job = futs[fut]
                try:
                    row = fut.result()
                except Exception as exc:
                    row = {"event": "game_error", "error": str(exc), **job}
                results.append(row)
                print(f"<< {job['pack']} #{job['game_index']} -> {row.get('event')}")

    append_jsonl(
        jsonl,
        {
            "ts": utc_now(),
            "event": "wave_done",
            "run_id": run_id,
            "played": len(results),
            "errors": sum(1 for r in results if r.get("event") == "game_error"),
        },
    )
    print("done.")
    print(
        "Report: python experiments/prompt-packs-jeff/report_jeff_ab.py "
        "--compare-wave-only --write"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
