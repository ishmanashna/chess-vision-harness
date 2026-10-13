from __future__ import annotations
import json, subprocess, time
from pathlib import Path

REPO = Path(r"C:\Users\jordi\Desktop\coding stuff\chess-vision-harness")
REPO83 = Path(r"C:\Users\jordi\Desktop\CODING~1\chess-vision-harness")
RUN = Path(r"C:\Users\jordi\Desktop\coding stuff\chess-vision-harness\experiments\mimo-v26-flash-play")
RUN83 = Path(r"C:\Users\jordi\Desktop\CODING~1\chess-vision-harness\experiments\mimo-v26-flash-play")
OC = Path(r"C:\Users\jordi\AppData\Roaming\npm\node_modules\opencode-ai\bin\opencode.exe")
BASE = "http://127.0.0.1:8765"
MODEL = "mimo-v2.6-flash"
OC_MODEL = "opencode/mimo-v2.6-flash-free"

import sys
sys.path.insert(0, str(REPO / "python" / "src"))
from chess_harness.api_keys import ApiKeyStore
import urllib.request, urllib.error

def http_json(method, url, key=None, body=None, timeout=60):
    data = None
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"error": raw}
        return e.code, payload

def mint(label):
    secrets = RUN / "secrets"
    secrets.mkdir(exist_ok=True)
    p = secrets / f"{label}.api_key"
    raw = ApiKeyStore().create(MODEL)
    p.write_text(raw, encoding="ascii")
    return raw

def write_runner(label, title, brief_path):
    runner = RUN / f"{label}-runner.ps1"
    out = RUN / f"launch-{label}.out.txt"
    err = RUN / f"launch-{label}.err.txt"
    body = (
        "$ErrorActionPreference = 'Continue'\n"
        f"$Brief = Get-Content -LiteralPath '{brief_path}' -Raw\n"
        f"Set-Location '{REPO83}'\n"
        f"& '{OC}' run --dir '{REPO83}' -m {OC_MODEL} --variant max --auto --title '{title}' -- $Brief\n"
    )
    runner.write_text(body, encoding="ascii")
    cmd = [
        "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        (
            f"$p = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File','{runner}') "
            f"-WorkingDirectory '{REPO83}' -RedirectStandardOutput '{out}' -RedirectStandardError '{err}' -PassThru -WindowStyle Hidden; "
            f"Set-Content -LiteralPath '{RUN / (label + '-runner.pid.txt')}' -Value $p.Id; Write-Output $p.Id"
        ),
    ]
    pid_s = subprocess.check_output(cmd, text=True, errors="replace").strip().splitlines()[-1].strip()
    return int(pid_s)

def main():
    seats = []

    # two AvE
    ave = [
        ("ave2", "stockfish-handicap:noise72", "black"),
        ("ave3", "stockfish-handicap:noise55", "white"),
    ]
    for label, opp, color in ave:
        key = mint(label)
        code, payload = http_json("POST", f"{BASE}/api/v1/games", key=key, body={"opponent": opp, "agent_color": color})
        if code >= 400 or not payload.get("ok"):
            raise SystemExit(f"{label} create failed {code} {payload}")
        gid = payload["game_id"]
        brief = payload.get("agent_brief") or ""
        # ask them to chain another AvE if they finish
        wrap = (
            "Play this AvE game to the end. If it finishes and you still have time, "
            "start ONE more AvE game with the same key vs stockfish-handicap:noise55 and play that too. "
            "Do not start puzzles or identify.\n\n"
        )
        brief_path = RUN / f"{label}-brief.txt"
        brief_path.write_text(wrap + brief, encoding="utf-8")
        (RUN / f"{label}-start.json").write_text(json.dumps({k:v for k,v in payload.items() if k != "agent_brief"}, indent=2), encoding="utf-8")
        title = f"mimo-v26-flash-{label}-{gid}"
        pid = write_runner(label, title, brief_path)
        seats.append({"label": label, "kind": "ave", "id": gid, "watch": f"{BASE}/g/{gid}", "public": f"https://chessvisionharness.pages.dev/g/{gid}", "opp": opp, "color": color, "pid": pid, "title": title})
        print(f"AVE {label} {gid} {color} vs {opp} pid={pid}", flush=True)

    # puzzle + identify seat
    key = mint("puz1")
    code, payload = http_json("POST", f"{BASE}/api/v1/puzzles/start", key=key)
    if code >= 400 or not payload.get("ok"):
        raise SystemExit(f"puzzle start failed {code} {payload}")
    aid = payload["attempt_id"]
    brief = payload.get("agent_brief") or ""
    wrap = (
        "JOB: complete EXACTLY 10 puzzles, then EXACTLY 10 board-identification attempts, then STOP.\n"
        "Use this Bearer key for every request.\n"
        "After each puzzle review, POST /api/v1/puzzles/start (same auth, no body) until you have 10 finished puzzle attempts.\n"
        "Then POST /api/v1/identify/start (same auth) and complete 10 identifies: GET board + board.txt, POST /answer with {\"pieces\": {square: piece}}.\n"
        "Do not start AvE games. Do not go past 10+10.\n\n"
    )
    brief_path = RUN / "puz1-brief.txt"
    brief_path.write_text(wrap + brief, encoding="utf-8")
    (RUN / "puz1-start.json").write_text(json.dumps({k:v for k,v in payload.items() if k != "agent_brief"}, indent=2), encoding="utf-8")
    title = f"mimo-v26-flash-puz1-{aid}"
    pid = write_runner("puz1", title, brief_path)
    seats.append({"label": "puz1", "kind": "puzzle+identify", "id": aid, "watch": f"{BASE}/p/{aid}", "public": f"https://chessvisionharness.pages.dev/p/{aid}", "pid": pid, "title": title})
    print(f"PUZ puz1 {aid} pid={pid}", flush=True)

    (RUN / "wave2-seats.json").write_text(json.dumps(seats, indent=2) + "\n", encoding="utf-8")

    # wait for sessions
    sessions = {}
    for attempt in range(24):
        time.sleep(5)
        try:
            listing = subprocess.check_output([str(OC), "session", "list", "--format", "json", "-n", "40"], cwd=str(REPO83), text=True, errors="replace", timeout=90)
            data = json.loads(listing)
        except Exception as e:
            print("session list fail", e, flush=True)
            continue
        if not isinstance(data, list):
            data = [data]
        for s in seats:
            if s["label"] in sessions:
                continue
            for row in data:
                title = str(row.get("title") or row.get("name") or "")
                sid = row.get("id") or row.get("sessionID") or row.get("session_id")
                if sid and (s["title"] in title or s["id"] in title):
                    sessions[s["label"]] = sid
                    s["session"] = sid
                    print(f"session {s['label']}={sid}", flush=True)
                    break
        if len(sessions) >= 3:
            break
        print(f"waiting sessions {len(sessions)}/3 try={attempt+1}", flush=True)

    # merge into session-ids.json
    path = RUN / "session-ids.json"
    existing = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    if not isinstance(existing, dict):
        existing = {}
    existing["ave1"] = existing.get("ave1") or {"session": (RUN/"session-id.txt").read_text(encoding="utf-8").strip() if (RUN/"session-id.txt").exists() else None}
    for s in seats:
        existing[s["label"]] = {"label": s["label"], "session": s.get("session"), "id": s["id"], "watch": s.get("watch"), "kind": s["kind"]}
    path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")

    print("=== WAVE2 DONE ===", flush=True)
    for s in seats:
        print(f"{s['label']} {s.get('watch')} ses={s.get('session')}", flush=True)
    return 0 if len(sessions) >= 3 else 2

if __name__ == "__main__":
    raise SystemExit(main())
