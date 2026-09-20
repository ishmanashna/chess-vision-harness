#!/usr/bin/env python3
"""MiMo free (OpenCode Zen CLI) baseline AvE wave — same calibrated slate as Jeff A/B.

5 games: 3x noise90 (~409) + 2x noise94 (~359). No prompt pack (baseline).
Abort immediately on rate-limit / FreeTier / hang — no sleep-retry loop.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SRC = REPO / "python" / "src"
sys.path.insert(0, str(SRC))
os.chdir(REPO)

from chess_harness.agent_http import AgentHttpClient, AgentHttpError
from chess_harness.agent_http.transport import urllib_transport
from chess_harness.board_text import format_board_text
from chess_harness.runner.adapters.typesafe import board_from_board_text, legal_uci
from chess_harness.runner.keys import ensure_harness_key
from chess_harness.runner.paths import keys_path

HARNESS = "http://127.0.0.1:8765"
MODEL = "mimo-v2.5"
OPENCODE = Path(r"C:\Users\jordi\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe")
OC_MODEL = "opencode/mimo-v2.5-free"
SLATE = [
    "stockfish-handicap:noise90",
    "stockfish-handicap:noise90",
    "stockfish-handicap:noise90",
    "stockfish-handicap:noise94",
    "stockfish-handicap:noise94",
]
TAG = "mimo-free-ab-baseline"
RUNS = HERE / "runs"
UCI_RE = re.compile(r"\b([a-h][1-8][a-h][1-8][qrbn]?)\b", re.I)
RATE_MARKERS = (
    "rate limit",
    "rate_limit",
    "FreeTierError",
    "429",
    "quota",
    "too many requests",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def opencode_pick_move(*, board_text: str, legal: List[str], timeout_sec: int = 180) -> str:
    if not OPENCODE.is_file():
        raise RuntimeError(f"missing opencode exe: {OPENCODE}")
    legal_s = ", ".join(legal)
    prompt = (
        "You are playing chess as the side to move. "
        "Reply with EXACTLY one UCI move from the legal list. No other words.\n\n"
        f"LEGAL: {legal_s}\n\nBOARD:\n{board_text}\n"
    )
    cmd = [
        str(OPENCODE),
        "run",
        "--format",
        "json",
        "--dir",
        str(REPO),
        "-m",
        OC_MODEL,
        prompt,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=str(REPO),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("opencode hang/timeout") from exc
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    low = out.lower()
    for m in RATE_MARKERS:
        if m.lower() in low:
            raise RuntimeError(f"opencode rate-limit/abort: {m}")
    if proc.returncode != 0:
        raise RuntimeError(f"opencode exit {proc.returncode}: {out[-500:]}")
    # Prefer last text event if JSON lines
    texts: List[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):
            t = ev.get("text") or ev.get("part") or ""
            if isinstance(t, dict):
                t = t.get("text") or ""
            if isinstance(t, str) and t.strip():
                texts.append(t)
            # nested
            for k in ("message", "delta", "content"):
                v = ev.get(k)
                if isinstance(v, str) and v.strip():
                    texts.append(v)
    blob = "\n".join(texts) if texts else out
    matches = UCI_RE.findall(blob)
    for m in reversed(matches):
        u = m.lower()
        if u in legal:
            return u
    # fallback first legal if model ignored list (still record)
    if matches:
        u = matches[-1].lower()
        if u in legal:
            return u
    raise RuntimeError(f"no legal UCI in opencode output: {blob[-400:]}")


def play_one(client: AgentHttpClient, opponent: str, jsonl: Path, idx: int) -> Dict[str, Any]:
    t0 = time.time()
    print(f">> mimo baseline #{idx} vs {opponent}", flush=True)
    try:
        created = client.create_game(opponent=opponent, agent_color="white", persist=True)
        game_id = str(created.get("game_id") or "")
        if not game_id:
            raise RuntimeError(f"create missing game_id: {created}")
    except Exception as exc:
        row = {
            "event": "game_error",
            "pack": "mimo-baseline",
            "game_index": idx,
            "opponent": opponent,
            "ok": False,
            "error": str(exc),
            "ts": utc_now(),
            "tag": TAG,
        }
        append_jsonl(jsonl, row)
        print(f"<< game_error {exc}", flush=True)
        return row

    plies = 0
    try:
        while True:
            st = client.status(game_id)
            status = str(st.get("status") or st.get("state") or "").lower()
            if status in {"finished", "over", "complete", "ended"} or st.get("result"):
                result = st.get("result")
                row = {
                    "event": "game_done",
                    "pack": "mimo-baseline",
                    "game_index": idx,
                    "opponent": opponent,
                    "game_id": game_id,
                    "result": result,
                    "ok": True,
                    "plies": plies,
                    "elapsed_sec": round(time.time() - t0, 1),
                    "ts": utc_now(),
                    "tag": TAG,
                    "run_id": jsonl.stem,
                }
                append_jsonl(jsonl, row)
                print(f"<< game_done game_id={game_id} result={result}", flush=True)
                return row
            # board text
            try:
                board_text = client.board_text(game_id)
            except Exception:
                # fallback status field
                board_text = str(st.get("board_text") or "")
                if not board_text:
                    raise
            board = board_from_board_text(board_text)
            legal = legal_uci(board)
            if not legal:
                raise RuntimeError("no legal moves but game not finished")
            move = opencode_pick_move(board_text=board_text, legal=legal)
            client.move(game_id, move)
            plies += 1
            if plies > 300:
                raise RuntimeError("ply cap 300")
    except Exception as exc:
        row = {
            "event": "game_error",
            "pack": "mimo-baseline",
            "game_index": idx,
            "opponent": opponent,
            "game_id": game_id,
            "ok": False,
            "error": str(exc),
            "plies": plies,
            "elapsed_sec": round(time.time() - t0, 1),
            "ts": utc_now(),
            "tag": TAG,
            "run_id": jsonl.stem,
        }
        append_jsonl(jsonl, row)
        print(f"<< game_error game_id={game_id} {exc}", flush=True)
        # stop whole wave on rate limit
        if "rate-limit" in str(exc).lower() or "freetier" in str(exc).lower():
            raise
        return row


def main() -> int:
    go = "--go" in sys.argv
    print("=== MiMo free OpenCode baseline wave PLAN ===")
    print(f"model:     {MODEL} via {OC_MODEL}")
    print(f"harness:   {HARNESS}")
    print(f"slate (5): {' | '.join(SLATE)}")
    print("note:      OpenCode free HTTP is blocked (FreeTierError); using CLI run only")
    if not go:
        print("\n[dry-run] pass --go to play")
        return 0

    transport = urllib_transport()
    api_key = ensure_harness_key(
        base_url=HARNESS,
        inscribed_id=MODEL,
        observation="text",
        transport=transport,
        path=keys_path(),
    )
    client = AgentHttpClient(HARNESS, api_key, model_id=MODEL, transport=transport)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    jsonl = RUNS / f"{run_id}.jsonl"
    print(f"run_id={run_id}")
    print(f"jsonl={jsonl}")
    append_jsonl(
        jsonl,
        {"event": "wave_start", "run_id": run_id, "tag": TAG, "slate": SLATE, "ts": utc_now()},
    )
    for i, opp in enumerate(SLATE, start=1):
        play_one(client, opp, jsonl, i)
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
