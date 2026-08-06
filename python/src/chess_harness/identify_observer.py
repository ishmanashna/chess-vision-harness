"""Public board-identification watching and replay (/i/{attempt_id}, public API).

Observer-safe by construction: while an attempt is active the published state
contains only the attempt id, agent display name, the current visible board,
and submission progress. The true placement, submitted placement, per-square
errors, and difficulty are never published before submission; replay unlocks
only after the attempt ends.
"""

from __future__ import annotations

import html
import io
from typing import Any, Dict

import chess
from PIL import Image, ImageDraw

from .ladder_display import FAVICON_LINKS, PUBLIC_SITE_HEADER, THEME_INIT_SCRIPT
from .models import ModelRegistry
from .puzzle_observer import CM_CHESSBOARD_VERSION, CM_CDN
from .render_pillow import ChessBoardRenderer

__all__ = [
    "observer_state",
    "replay_payload",
    "render_identify_board_png",
    "render_answer_overlay_png",
    "public_attempt_row",
    "render_identify_watch_page",
]


def _agent_name(record: Dict[str, Any]) -> str:
    try:
        model = ModelRegistry().get(str(record.get("model_id") or ""))
        if model:
            return str(model.get("name") or model.get("id") or record["model_id"])
    except Exception:
        pass
    return str(record.get("model_id") or "unknown")


def observer_state(record: Dict[str, Any]) -> Dict[str, Any]:
    """Observer-safe live state (never leaks placements or difficulty)."""
    finished = record.get("status") == "finished"
    state: Dict[str, Any] = {
        "ok": True,
        "attempt_id": record["attempt_id"],
        "agent_name": _agent_name(record),
        "status": record.get("status", "active"),
        "result": record.get("result") if finished else None,
        "submitted_count": 1 if record.get("submitted_pieces") else 0,
        "fen": record.get("corpus_fen", chess.STARTING_FEN),
        "started_at": record.get("started_at"),
        "updated_at": record.get("updated_at"),
        "finished_at": record.get("finished_at") if finished else None,
    }
    if finished:
        score = record.get("score") or {}
        state["accuracy"] = score.get("accuracy")
        state["score"] = {
            "total_pieces": score.get("total_pieces"),
            "exact": score.get("exact"),
            "missing": score.get("missing"),
            "extra": score.get("extra"),
            "misidentified": score.get("misidentified"),
            "full_position": score.get("full_position"),
        }
        state["difficulty"] = record.get("puzzle_rating")
    return state


def replay_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """Full replay (submitted vs correct, per-square errors); only after finish."""
    return {
        "ok": True,
        "attempt_id": record["attempt_id"],
        "agent_name": _agent_name(record),
        "result": record.get("result"),
        "failure_reason": record.get("failure_reason"),
        "score": record.get("score"),
        "per_square": record.get("per_square"),
        "submitted_pieces": record.get("submitted_pieces"),
        "correct_pieces": record["correct_pieces"],
        "difficulty": record.get("puzzle_rating"),
        "started_at": record.get("started_at"),
        "submitted_at": record.get("submitted_at"),
        "finished_at": record.get("finished_at"),
    }


def render_identify_board_png(record: Dict[str, Any]) -> bytes:
    """Answer-safe board PNG: the visible position, no highlights."""
    return ChessBoardRenderer().render_board_bytes(
        chess.Board(record.get("corpus_fen", chess.STARTING_FEN))
    )


def render_answer_overlay_png(record: Dict[str, Any]) -> bytes:
    """Post-completion answer board: green = exact, red = wrong/missing/extra."""
    renderer = ChessBoardRenderer()
    base = renderer.render_board_bytes(
        chess.Board(record.get("corpus_fen", chess.STARTING_FEN))
    )
    image = Image.open(io.BytesIO(base)).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    size = renderer.square_size
    for entry in record.get("per_square") or []:
        square = str(entry.get("square") or "")
        if len(square) != 2:
            continue
        file_index = chess.FILE_NAMES.index(square[0])
        rank = int(square[1]) - 1
        x = renderer.coord_margin + file_index * size
        y = (7 - rank) * size
        fill = (0, 200, 0, 80) if entry.get("status") == "exact" else (255, 45, 45, 90)
        draw.rectangle([x, y, x + size, y + size], fill=fill)
    buf = io.BytesIO()
    Image.alpha_composite(image, overlay).convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def public_attempt_row(record: Dict[str, Any]) -> Dict[str, Any]:
    """One discovery row for the public browse list."""
    finished = record.get("status") == "finished"
    row: Dict[str, Any] = {
        "attempt_id": record["attempt_id"],
        "agent_name": _agent_name(record),
        "status": record.get("status"),
        "result": record.get("result") if finished else None,
        "submitted_count": 1 if record.get("submitted_pieces") else 0,
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at") if finished else None,
        "watch_url": f"/i/{record['attempt_id']}",
    }
    if finished:
        score = record.get("score") or {}
        row["accuracy"] = score.get("accuracy")
    return row


def render_identify_watch_page(attempt_id: str) -> str:
    """Spectator watch/replay HTML for /i/{attempt_id}."""
    aid = html.escape(attempt_id, quote=True)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
    {FAVICON_LINKS}
    <title>Identify {aid} · Chess Vision Harness</title>
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
    #state-result{{font-weight:700}}
    .board-col{{display:flex;justify-content:center}}
    .board-stack{{display:inline-flex;flex-direction:column;border:1px solid var(--border-strong);border-radius:10px;overflow:hidden;background:var(--surface);box-shadow:0 1px 4px var(--shadow,rgba(0,0,0,.06))}}
    .board-label{{padding:11px 16px;text-align:center;font-size:.93em;font-weight:600;background:var(--bg-elevated);color:var(--text)}}
    .puzzle-board-wrap{{width:min(480px,calc(100vh - 240px),calc(100vw - 760px));aspect-ratio:1;position:relative;overflow:hidden;background:var(--surface)}}
    .puzzle-board-wrap .cm-chessboard{{width:100%;height:100%}}
    .answer-img-wrap{{margin-top:16px;display:none}}
    .answer-img-wrap img{{width:min(480px,calc(100vh - 300px),calc(100vw - 780px));height:auto;border:1px solid var(--border-strong);border-radius:10px}}
    .replay-panel{{margin-top:16px}}
    .results-table{{width:100%;border-collapse:collapse;font-size:.84em}}
    .results-table th,.results-table td{{padding:5px 8px;border-bottom:1px solid var(--border);text-align:left}}
    .results-table .badge{{display:inline-block;border-radius:999px;padding:1px 9px;font-size:.74em}}
    .badge.exact{{background:rgba(0,180,0,.14);color:#2e7d32}}
    .badge.missing,.badge.extra,.badge.wrong_color,.badge.wrong_type{{background:rgba(220,40,40,.12);color:#c0392b}}
    @media(max-width:900px){{
      .layout{{grid-template-columns:1fr;gap:20px;width:100%}}
      .puzzle-board-wrap{{width:100%;max-width:480px}}
      .answer-img-wrap img{{width:100%;max-width:480px}}
    }}
    </style></head><body class="identify-view" data-attempt-id="{aid}">
    <div class="wrap">
    {PUBLIC_SITE_HEADER}
    <main>
    <div class="layout">
      <aside class="info-col">
        <div class="info-card">
          <h2>Identification</h2>
          <dl class="meta-grid" id="meta"></dl>
        </div>
        <div class="info-card">
          <h2>Attempt state</h2>
          <dl class="meta-grid" id="state-meta">
            <dt>Status</dt><dd id="state-status">Loading…</dd>
            <dt>Result</dt><dd id="state-result">—</dd>
            <dt>Accuracy</dt><dd id="state-accuracy">—</dd>
            <dt>Submitted</dt><dd id="state-submitted">0</dd>
            <dt>Difficulty</dt><dd id="state-difficulty">—</dd>
          </dl>
        </div>
      </aside>
      <div class="board-col">
        <div class="board-stack">
          <div class="board-label" id="board-label">Position</div>
          <div class="puzzle-board-wrap" id="board-wrap">
            <div id="board" class="puzzle-board" role="img" aria-label="position board"></div>
          </div>
          <div class="board-label">White at bottom · a1 bottom-left</div>
        </div>
        <div class="answer-img-wrap" id="answer-wrap">
          <img id="answer-img" alt="true placement (green = exact, red = mismatch)" />
        </div>
        <div class="replay-panel" id="replay-panel" hidden>
          <h2>Placement review</h2>
          <div class="table-wrap">
            <table class="results-table">
              <thead><tr><th>Square</th><th>Expected</th><th>Submitted</th><th>Status</th></tr></thead>
              <tbody id="results-body"></tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
    </main>
    <footer class="site-footer">
      <p>Chess Vision Harness · <a href="https://github.com/ishmanashna/chess-vision-harness">Source on GitHub</a></p>
    </footer>
    </div>
    <script src="/js/common.js"></script>
    <script type="module" src="/js/identify-watch.js"></script>
    </body></html>"""