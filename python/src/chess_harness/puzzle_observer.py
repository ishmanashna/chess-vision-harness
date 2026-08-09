"""Public puzzle watching and replay (/p/{attempt_id}, /api/v1/puzzles/public/*).

Observer-safe by construction: while an attempt is active the published state
contains only the attempt id, agent display name, imported difficulty, the
current visible board, the agent's submitted and opponent moves as plain SAN
(they are not secret — only the solution is), the attempt-chain key, and move
counts. The solution, hidden FENs, and puzzle id are never published before
completion; replay (solution line, submitted line, per-ply FENs, rating
changes, source link) unlocks only after the attempt ends. Themes are never
published on any public surface: they stay only inside attempt/puzzle records.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List

import chess

from .ladder_display import FAVICON_LINKS, PUBLIC_SITE_HEADER, THEME_INIT_SCRIPT
from .models import ModelRegistry
from .puzzle_store import PuzzleStore
from .render_pillow import ChessBoardRenderer

__all__ = [
    "observer_state",
    "replay_payload",
    "render_observer_board_png",
    "render_puzzle_watch_page",
    "CM_CHESSBOARD_VERSION",
]

CM_CHESSBOARD_VERSION = "8.7.2"
CM_CDN = f"https://cdn.jsdelivr.net/npm/cm-chessboard@{CM_CHESSBOARD_VERSION}"


def san_moves(
    start_fen: str, submitted: List[str], opponent: List[str]
) -> tuple[List[str], List[str]]:
    """SAN labels for the submitted agent moves and opponent replies.

    Replays the known move history from the start position. Both lists were
    validated as legal when recorded, so ``board.san`` cannot raise here.
    """
    board = chess.Board(start_fen)
    agent_labels: List[str] = []
    opponent_labels: List[str] = []
    for index, uci in enumerate(submitted):
        agent = chess.Move.from_uci(uci)
        agent_labels.append(board.san(agent))
        board.push(agent)
        if index < len(opponent):
            reply = chess.Move.from_uci(opponent[index])
            opponent_labels.append(board.san(reply))
            board.push(reply)
    return agent_labels, opponent_labels


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
    """Observer-safe live state (never leaks solution or puzzle id)."""
    finished = record.get("status") == "finished"
    submitted = list(record.get("submitted_moves") or [])
    opponent = list(record.get("opponent_moves") or [])
    agent_moves, opponent_moves = san_moves(
        record.get("start_fen", record.get("board_fen")), submitted, opponent
    )
    return {
        "ok": True,
        "attempt_id": record["attempt_id"],
        "key": record.get("key_fingerprint"),
        "agent_name": _agent_name(record),
        "status": record.get("status", "active"),
        "result": record.get("result") if finished else None,
        "moves_played": len(submitted),
        "submitted_moves": agent_moves,
        "opponent_moves": opponent_moves,
        "puzzle_rating": int(record.get("puzzle_rating") or 0),
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
        "key": record.get("key_fingerprint"),
        "agent_name": _agent_name(record),
        "status": record.get("status"),
        "result": record.get("result") if finished else None,
        "moves_played": len(record.get("submitted_moves") or []),
        "puzzle_rating": int(record.get("puzzle_rating") or 0),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at") if finished else None,
        "watch_url": f"/p/{record['attempt_id']}",
    }


def render_puzzle_watch_page(attempt_id: str) -> str:
    """Spectator watch/replay HTML for /p/{attempt_id} (game-spectator grid family)."""
    aid = html.escape(attempt_id, quote=True)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
    {FAVICON_LINKS}
    <title>Puzzle {aid} · Chess Vision Harness</title>
    {THEME_INIT_SCRIPT}
    <link rel="stylesheet" href="/css/site.css"/>
    <link rel="stylesheet" href="{CM_CDN}/assets/chessboard.css"/>
    <style>
    .layout{{display:grid;grid-template-columns:minmax(300px,400px) minmax(320px,480px) minmax(240px,320px);gap:16px;align-items:start;justify-content:center;width:fit-content;max-width:100%;margin:0 auto}}
    .info-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:18px 20px}}
    .info-card h2{{margin:0 0 10px;font-size:.7em;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--faint)}}
    .meta-grid{{display:grid;grid-template-columns:minmax(5.5rem,42%) minmax(5rem,1fr);gap:6px 12px;font-size:.86em;line-height:1.45}}
    .meta-grid dt{{color:var(--faint);margin:0;overflow-wrap:break-word;word-break:normal;min-width:0}}
    .meta-grid dd{{margin:0;color:var(--text-secondary);overflow-wrap:break-word;word-break:normal;min-width:0}}
    .meta-grid > [hidden]{{display:none!important}}
    #state-result{{font-weight:700}}
    .chain-list{{list-style:none;margin:0;padding:0;font-size:.86em}}
    .chain-list li{{padding:6px 0;border-bottom:1px solid var(--row)}}
    .chain-list li:last-child{{border-bottom:none}}
    .chain-list a{{color:var(--link);text-decoration:none}}
    .chain-list a:hover{{text-decoration:underline}}
    .chain-list .chain-you{{color:var(--faint);font-style:italic}}
    .follow-banner{{display:none;margin-top:12px;padding:8px 12px;border:1px solid var(--accent,#6b8afd);border-radius:6px;font-size:.84em;color:var(--accent,#6b8afd)}}
    .board-col{{display:flex;justify-content:center}}
    .board-stack{{display:inline-flex;flex-direction:column;border:1px solid var(--border-strong);border-radius:10px;overflow:hidden;background:var(--surface);box-shadow:0 1px 4px var(--shadow,rgba(0,0,0,.06))}}
    .board-label{{padding:11px 16px;text-align:center;font-size:.93em;font-weight:600;background:var(--bg-elevated);color:var(--text)}}
    .board-label .sub{{display:block;font-size:.76em;font-weight:400;color:var(--faint);margin-top:3px}}
    .puzzle-board-wrap{{width:min(480px,calc(100vh - 240px),calc(100vw - 820px));aspect-ratio:1;position:relative;overflow:hidden;background:var(--surface)}}
    .puzzle-board-wrap .cm-chessboard{{width:100%;height:100%}}
    .moves-col{{display:flex;flex-direction:column;min-height:0;max-height:calc(100vh - 140px)}}
    .moves-col .panel{{background:var(--surface);border:1px solid var(--border);border-radius:8px;display:flex;flex-direction:column;flex:1;min-height:200px;overflow:hidden}}
    .moves-col .panel h2{{padding:14px 16px 0;margin:0;font-size:.7em;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--faint)}}
    .moves-scroll{{overflow-y:auto;flex:1;padding:8px 12px 14px}}
    .move-row{{display:grid;grid-template-columns:26px 1fr 1fr;gap:8px;padding:7px 4px;font-size:.88em;border-bottom:1px solid var(--row)}}
    .move-row:last-child{{border-bottom:none}}
    .move-row .mn{{color:var(--faint);text-align:right;font-size:.82em}}
    .move-row .w,.move-row .b{{cursor:pointer;border-radius:3px;padding:2px 4px;min-height:1.2em}}
    .move-row .w:empty,.move-row .b:empty{{cursor:default;pointer-events:none}}
    .move-row .w.is-wrong{{font-weight:700;color:var(--danger,#c0392b)}}
    .move-row .w.on,.move-row .b.on{{font-weight:700;background:var(--row)}}
    @media(max-width:960px){{
      .layout{{grid-template-columns:1fr;gap:20px;width:100%;justify-content:stretch}}
      .moves-col{{max-height:320px}}
      .puzzle-board-wrap{{width:100%;max-width:480px}}
    }}
    </style></head><body class="puzzle-view" data-attempt-id="{aid}">
    <div class="wrap">
    {PUBLIC_SITE_HEADER}
    <main>
    <div class="layout">
      <aside class="col info-col">
        <div class="info-card">
          <h2>Puzzle info</h2>
          <dl class="meta-grid" id="meta">
            <dt>Attempt</dt><dd>Loading…</dd>
            <dt>Agent</dt><dd>—</dd>
            <dt id="state-puzzle-label" hidden>Puzzle id</dt><dd id="state-puzzle" hidden>—</dd>
            <dt id="state-source-label" hidden>Source</dt><dd id="state-source" hidden>—</dd>
          </dl>
        </div>
        <div class="info-card">
          <h2>Attempt state</h2>
          <dl class="meta-grid" id="state-meta">
            <dt>Status</dt><dd id="state-status">Loading…</dd>
            <dt>Result</dt><dd id="state-result">—</dd>
            <dt id="state-rating-label" hidden>Rating</dt><dd id="state-rating" hidden>—</dd>
            <dt>Difficulty</dt><dd id="state-difficulty">—</dd>
            <dt id="state-metrics-label">Agent rating</dt><dd id="state-agent-rating">—</dd>
            <dt>Deviation</dt><dd id="state-deviation">—</dd>
            <dt>Attempts</dt><dd id="state-attempts">—</dd>
            <dt>Solves</dt><dd id="state-solves">—</dd>
          </dl>
        </div>
        <div class="info-card">
          <h2>Attempt chain</h2>
          <p class="chain-empty" id="chain-empty" style="margin:0;font-size:.84em;color:var(--faint)">No previous attempts for this agent yet.</p>
          <ul class="chain-list" id="chain" hidden></ul>
          <div class="follow-banner" id="follow-banner"></div>
        </div>
      </aside>
      <div class="col board-col" id="board-col">
        <div class="board-stack">
          <div class="board-label">Puzzle<span class="sub">white at bottom · a1 bottom-left</span></div>
          <div class="puzzle-board-wrap" id="board-wrap">
            <div id="board" class="puzzle-board" role="img" aria-label="puzzle board"></div>
          </div>
          <div class="board-label" id="board-label-turn">White to move</div>
        </div>
      </div>
      <aside class="col moves-col" id="moves-col">
        <div class="panel">
          <h2 id="moves-heading">Moves</h2>
          <div class="moves-scroll" id="mv"></div>
        </div>
      </aside>
    </div>
    </main>
    <footer class="site-footer">
      <p>Chess Vision Harness · <a href="https://github.com/ishmanashna/chess-vision-harness">Source on GitHub</a></p>
    </footer>
    </div>
    <script src="/js/common.js"></script>
    <script type="module" src="/js/puzzle-watch.js"></script>
    </body></html>"""
