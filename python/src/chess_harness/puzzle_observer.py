"""Public puzzle watching and replay (/p/{attempt_id}, /api/v1/puzzles/public/*).

Observer-safe by construction: while an attempt is active the published state
contains only the attempt id, agent display name, imported difficulty, safe
(non-spoiler) themes, the current visible board, and submitted-move count.
The solution, submitted move list, and hidden FENs are never published before
completion; replay (solution line, submitted line, per-ply FENs, rating
changes, source link, themes) unlocks only after the attempt ends.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional

import chess

from .ladder_display import FAVICON_LINKS, PUBLIC_SITE_HEADER, THEME_INIT_SCRIPT
from .models import ModelRegistry
from .puzzle_store import PuzzleStore
from .render_pillow import ChessBoardRenderer

__all__ = [
    "safe_themes",
    "observer_state",
    "replay_payload",
    "render_observer_board_png",
    "render_puzzle_watch_page",
    "CM_CHESSBOARD_VERSION",
]

CM_CHESSBOARD_VERSION = "8.7.2"
CM_CDN = f"https://cdn.jsdelivr.net/npm/cm-chessboard@{CM_CHESSBOARD_VERSION}"

# Themes that reveal the winning idea are withheld from observers until the
# attempt completes; the rest are "safe" (non-answer) tags.
SPOILER_MARKERS = ("mate", "sacrifice")


def safe_themes(themes: Optional[list]) -> List[str]:
    return [
        str(theme)
        for theme in (themes or [])
        if not any(marker in str(theme).lower() for marker in SPOILER_MARKERS)
    ]


def _agent_name(record: Dict[str, Any]) -> str:
    try:
        model = ModelRegistry().get(str(record.get("model_id") or ""))
        if model:
            return str(model.get("name") or model.get("id") or record["model_id"])
    except Exception:
        pass
    return str(record.get("model_id") or "unknown")


def _puzzle(record: Dict[str, Any]) -> Dict[str, Any]:
    return PuzzleStore().get(str(record.get("puzzle_id") or "")) or {}


def observer_state(record: Dict[str, Any]) -> Dict[str, Any]:
    """Observer-safe live state (never leaks solution/submitted moves)."""
    finished = record.get("status") == "finished"
    return {
        "ok": True,
        "attempt_id": record["attempt_id"],
        "agent_name": _agent_name(record),
        "status": record.get("status", "active"),
        "result": record.get("result") if finished else None,
        "moves_played": len(record.get("submitted_moves") or []),
        "puzzle_rating": int(record.get("puzzle_rating") or 0),
        "themes": safe_themes(_puzzle(record).get("themes")),
        "fen": record.get("board_fen", chess.STARTING_FEN),
        "started_at": record.get("started_at"),
        "updated_at": record.get("updated_at"),
        "finished_at": record.get("finished_at") if finished else None,
    }


def _build_plies(
    start_fen: str,
    submitted: List[str],
    opponent: List[str],
) -> List[Dict[str, Any]]:
    """Per-ply FEN + SAN labels for replay scrubbing (start -> final)."""
    board = chess.Board(start_fen)
    plies: List[Dict[str, Any]] = []
    count = len(submitted)
    for index in range(count):
        agent = chess.Move.from_uci(submitted[index])
        agent_label = f"{index + 1}. {board.san(agent)}"
        board.push(agent)
        plies.append({"fen": board.fen(), "label": agent_label})
        if index < len(opponent):
            reply = chess.Move.from_uci(opponent[index])
            reply_label = f"{index + 1}... {board.san(reply)}"
            board.push(reply)
            plies.append({"fen": board.fen(), "label": reply_label})
    return plies


def replay_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """Full replay; only call after the attempt finished."""
    puzzle = _puzzle(record)
    submitted = list(record.get("submitted_moves") or [])
    opponent = list(record.get("opponent_moves") or [])
    return {
        "ok": True,
        "attempt_id": record["attempt_id"],
        "puzzle_id": record["puzzle_id"],
        "agent_name": _agent_name(record),
        "result": record.get("result"),
        "failure_reason": record.get("failure_reason"),
        "first_wrong_move": record.get("first_wrong_move"),
        "submitted_moves": submitted,
        "opponent_moves": opponent,
        "solution_moves": list(record.get("solution_moves") or []),
        "start_fen": record.get("start_fen", record.get("board_fen")),
        "plies": _build_plies(
            record.get("start_fen", record.get("board_fen")),
            submitted,
            opponent,
        ),
        "themes": list(puzzle.get("themes") or []),
        "source_link": puzzle.get("game_url") or "",
        "puzzle_rating": int(record.get("puzzle_rating") or 0),
        "rating_before": record.get("rating_before"),
        "rating_after": record.get("rating_after"),
        "rating_change": record.get("rating_change"),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at"),
    }


def render_observer_board_png(record: Dict[str, Any]) -> bytes:
    """Answer-safe board PNG: the current visible position, no move highlights."""
    board = chess.Board(record.get("board_fen", chess.STARTING_FEN))
    return ChessBoardRenderer().render_board_bytes(board)


def public_attempt_row(record: Dict[str, Any]) -> Dict[str, Any]:
    """One discovery row for the public browse list."""
    finished = record.get("status") == "finished"
    return {
        "attempt_id": record["attempt_id"],
        "agent_name": _agent_name(record),
        "status": record.get("status"),
        "result": record.get("result") if finished else None,
        "moves_played": len(record.get("submitted_moves") or []),
        "puzzle_rating": int(record.get("puzzle_rating") or 0),
        "themes": safe_themes(_puzzle(record).get("themes")),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at") if finished else None,
        "watch_url": f"/p/{record['attempt_id']}",
    }


def render_puzzle_watch_page(attempt_id: str) -> str:
    """Spectator watch/replay HTML for /p/{attempt_id}."""
    aid = html.escape(attempt_id, quote=True)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
    {FAVICON_LINKS}
    <title>Puzzle {aid} · Chess Vision Harness</title>
    {THEME_INIT_SCRIPT}
    <link rel="stylesheet" href="/css/site.css"/>
    <link rel="stylesheet" href="{CM_CDN}/assets/chessboard.css"/>
    <style>
    .layout{{display:grid;grid-template-columns:minmax(300px,400px) minmax(320px,480px);gap:20px;align-items:start;justify-content:center;width:fit-content;max-width:100%;margin:0 auto}}
    .info-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:18px 20px}}
    .info-card h2{{margin:0 0 10px;font-size:.7em;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--faint)}}
    .meta-grid{{display:grid;grid-template-columns:minmax(5.5rem,42%) minmax(5rem,1fr);gap:6px 12px;font-size:.86em;line-height:1.45}}
    .meta-grid dt{{color:var(--faint);margin:0;overflow-wrap:break-word;min-width:0}}
    .meta-grid dd{{margin:0;color:var(--text-secondary);overflow-wrap:break-word;min-width:0}}
    .meta-grid > [hidden]{{display:none!important}}
    #state-result{{font-weight:700}}
    .themes-list{{display:flex;flex-wrap:wrap;gap:6px}}
    .theme-tag{{background:var(--row);border:1px solid var(--border);border-radius:999px;padding:2px 10px;font-size:.78em;color:var(--text-secondary)}}
    .board-col{{display:flex;justify-content:center}}
    .board-stack{{display:inline-flex;flex-direction:column;border:1px solid var(--border-strong);border-radius:10px;overflow:hidden;background:var(--surface);box-shadow:0 1px 4px var(--shadow,rgba(0,0,0,.06))}}
    .board-label{{padding:11px 16px;text-align:center;font-size:.93em;font-weight:600;background:var(--bg-elevated);color:var(--text)}}
    .puzzle-board-wrap{{width:min(480px,calc(100vh - 240px),calc(100vw - 760px));aspect-ratio:1;position:relative;overflow:hidden;background:var(--surface)}}
    .puzzle-board-wrap .cm-chessboard{{width:100%;height:100%}}
    .replay-panel{{margin-top:16px}}
    .replay-controls{{display:flex;gap:8px;align-items:center;margin-bottom:10px}}
    .replay-controls button{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:4px 12px;font:inherit;font-size:.84rem;color:var(--text);cursor:pointer}}
    .replay-controls button:hover{{border-color:var(--border-strong)}}
    .replay-controls button:disabled{{opacity:.4;cursor:default}}
    .replay-steps{{display:flex;flex-wrap:wrap;gap:6px}}
    .step-chip{{background:var(--row);border:1px solid var(--border);border-radius:6px;padding:4px 10px;font-size:.82em;color:var(--text-secondary);cursor:pointer}}
    .step-chip.on{{background:var(--accent,#6b8afd);color:#fff;border-color:transparent}}
    .step-chip.is-wrong{{border-color:var(--danger,#c0392b)}}
    @media(max-width:900px){{
      .layout{{grid-template-columns:1fr;gap:20px;width:100%}}
      .puzzle-board-wrap{{width:100%;max-width:480px}}
    }}
    </style></head><body class="puzzle-view" data-attempt-id="{aid}">
    <div class="wrap">
    {PUBLIC_SITE_HEADER}
    <main>
    <div class="layout">
      <aside class="info-col">
        <div class="info-card">
          <h2>Puzzle info</h2>
          <dl class="meta-grid" id="meta"></dl>
        </div>
        <div class="info-card">
          <h2>Attempt state</h2>
          <dl class="meta-grid" id="state-meta">
            <dt>Status</dt><dd id="state-status">Loading…</dd>
            <dt>Result</dt><dd id="state-result">—</dd>
            <dt>Moves</dt><dd id="state-moves">0</dd>
            <dt>Difficulty</dt><dd id="state-rating">—</dd>
            <dt>Themes</dt><dd id="state-themes"><span class="themes-list"></span></dd>
          </dl>
        </div>
      </aside>
      <div class="board-col">
        <div class="board-stack">
          <div class="board-label" id="board-label">Puzzle</div>
          <div class="puzzle-board-wrap" id="board-wrap">
            <div id="board" class="puzzle-board" role="img" aria-label="puzzle board"></div>
          </div>
          <div class="board-label" id="board-label-turn">White to move</div>
        </div>
        <div class="replay-panel" id="replay-panel" hidden>
          <h2>Replay</h2>
          <div class="replay-controls">
            <button type="button" id="replay-prev">◀ Prev</button>
            <button type="button" id="replay-next">Next ▶</button>
            <span id="replay-pos" style="font-size:.84rem;color:var(--faint)"></span>
          </div>
          <div class="replay-steps" id="replay-steps"></div>
        </div>
      </div>
    </div>
    </main>
    <footer class="site-footer">
      <p>Chess Vision Harness · <a href="https://github.com/ishmanashna/chess-vision-harness">Source on GitHub</a></p>
    </footer>
    </div>
    <script src="/js/common.js"></script>
    <script type="module" src="/js/puzzle-watch.js"></script>
    </body></html>"""
