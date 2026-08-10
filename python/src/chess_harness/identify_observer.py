"""Public board-identification watching and replay (/i/{attempt_id}, public API).

Observer-safe by construction: while an attempt is active the published state
contains only the attempt id, agent display name, the attempt-chain key, the
current visible board, and submission progress. The true placement, submitted
placement, per-square errors, and difficulty are never published before
submission; replay unlocks only after the attempt ends.
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
        "key": record.get("key_fingerprint"),
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
        state["full_position"] = score.get("full_position")
        state["total_pieces"] = score.get("total_pieces")
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
        "key": record.get("key_fingerprint"),
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
        row["full_position"] = score.get("full_position")
        row["total_pieces"] = score.get("total_pieces")
        row["difficulty"] = record.get("puzzle_rating")
    return row


def render_identify_watch_page(attempt_id: str) -> str:
    """Spectator watch/replay HTML for /i/{attempt_id} (game-spectator grid family)."""
    aid = html.escape(attempt_id, quote=True)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
    {FAVICON_LINKS}
    <title>Identify {aid} · Chess Vision Harness</title>
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
    .answer-img-wrap{{margin-top:14px;display:none}}
    .answer-img-wrap img{{width:100%;border:1px solid var(--border-strong);border-radius:10px}}
    .answer-img-wrap .cap{{padding:8px 2px 0;font-size:.78em;color:var(--faint);text-align:center}}
    .moves-col{{display:flex;flex-direction:column;min-height:0;max-height:calc(100vh - 140px)}}
    .moves-col .panel{{background:var(--surface);border:1px solid var(--border);border-radius:8px;display:flex;flex-direction:column;flex:1;min-height:200px;overflow:hidden}}
    .moves-col .panel h2{{padding:14px 16px 0;margin:0;font-size:.7em;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--faint)}}
    .moves-scroll{{overflow-y:auto;flex:1;padding:8px 12px 14px}}
    .results-table{{width:100%;border-collapse:collapse;font-size:.84em;margin-top:8px}}
    .results-table th,.results-table td{{padding:5px 8px;border-bottom:1px solid var(--border);text-align:left;color:var(--text-secondary)}}
    .results-table th{{color:var(--faint);font-size:.78em;text-transform:uppercase;letter-spacing:.04em}}
    .results-table .badge{{display:inline-block;border-radius:999px;padding:1px 9px;font-size:.74em}}
    .badge.exact{{background:rgba(0,180,0,.14);color:#2e7d32}}
    .badge.missing,.badge.extra,.badge.wrong_color,.badge.wrong_type{{background:rgba(220,40,40,.12);color:#c0392b}}
    @media(max-width:960px){{
      .layout{{grid-template-columns:1fr;gap:20px;width:100%;justify-content:stretch}}
      .moves-col{{max-height:360px}}
      .puzzle-board-wrap{{width:100%;max-width:480px}}
    }}
    </style></head><body class="identify-view" data-attempt-id="{aid}">
    <div class="wrap">
    {PUBLIC_SITE_HEADER}
    <main>
    <div class="layout">
      <aside class="col info-col">
        <div class="info-card">
          <h2>Identification</h2>
          <dl class="meta-grid" id="meta">
            <dt>Attempt</dt><dd>Loading…</dd>
            <dt>Agent</dt><dd>—</dd>
          </dl>
        </div>
        <div class="info-card">
          <h2>Attempt state</h2>
          <dl class="meta-grid" id="state-meta">
            <dt>Status</dt><dd id="state-status">Loading…</dd>
            <dt>Result</dt><dd id="state-result">—</dd>
            <dt>Accuracy</dt><dd id="state-accuracy">—</dd>
            <dt>Full position</dt><dd id="state-full-position">—</dd>
            <dt>Difficulty</dt><dd id="state-difficulty">—</dd>
            <dt>Submitted</dt><dd id="state-submitted">0</dd>
            <dt>Agent accuracy</dt><dd id="state-agent-rate">—</dd>
            <dt>Full-position rate</dt><dd id="state-agent-full">—</dd>
            <dt>Attempts</dt><dd id="state-attempts">—</dd>
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
          <div class="board-label">Position</div>
          <div class="puzzle-board-wrap" id="board-wrap">
            <div id="board" class="puzzle-board" role="img" aria-label="position board"></div>
          </div>
          <div class="board-label" id="board-label">Identification board</div>
        </div>
        <div class="answer-img-wrap" id="answer-wrap">
          <img id="answer-img" alt="true placement (green = exact, red = mismatch)" />
          <div class="cap">Green squares were placed exactly; red squares were wrong, missing, or extra.</div>
        </div>
      </div>
      <aside class="col moves-col" id="moves-col">
        <div class="panel">
          <h2 id="moves-heading">Placement review</h2>
          <div class="moves-scroll" id="mv">
            <p style="color:var(--faint);margin:0">
              Per-square review unlocks after the attempt ends.
            </p>
          </div>
        </div>
      </aside>
    </div>
    </main>
    <footer class="site-footer">
      <p>Chess Vision Harness · <a href="https://github.com/ishmanashna/chess-vision-harness">Source on GitHub</a></p>
    </footer>
    </div>
    <script src="/js/common.js"></script>
    <script type="module" src="/js/identify-watch.js"></script>
    </body></html>"""