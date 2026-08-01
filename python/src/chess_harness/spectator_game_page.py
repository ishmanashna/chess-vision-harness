"""Spectator game view HTML for /g/{game_id} with validated, escaped output."""

from __future__ import annotations

import html

from .ladder_display import FAVICON_LINKS, PUBLIC_SITE_HEADER, THEME_INIT_SCRIPT

__all__ = ["render_game_view_page", "CM_CHESSBOARD_VERSION", "CM_CDN"]

# Pin same cm-chessboard build as Playground (play_page.py).
CM_CHESSBOARD_VERSION = "8.7.2"
CM_CDN = f"https://cdn.jsdelivr.net/npm/cm-chessboard@{CM_CHESSBOARD_VERSION}"


def render_game_view_page(game_id: str) -> str:
    """Return spectator game HTML. Caller must validate game_id first."""
    gid = html.escape(game_id, quote=True)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
    {FAVICON_LINKS}
    <title>{gid} · Chess Vision Harness</title>
    {THEME_INIT_SCRIPT}
    <link rel="stylesheet" href="/css/site.css"/>
    <link rel="stylesheet" href="{CM_CDN}/assets/chessboard.css"/>
    <link rel="stylesheet" href="{CM_CDN}/assets/extensions/markers/markers.css"/>
    <style>
    .layout{{display:grid;grid-template-columns:minmax(300px,400px) max-content minmax(240px,320px);gap:16px;align-items:start;justify-content:center;width:fit-content;max-width:100%;margin:0 auto}}
    .col h2{{margin:0 0 12px;font-size:.7em;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--faint)}}
    .info-col{{display:flex;flex-direction:column;gap:12px;min-height:0}}
    .info-col-head{{display:flex;align-items:center;justify-content:flex-end;gap:10px;min-height:1.5rem;flex-shrink:0}}
    .info-col-head:has(#info-panel-toggle[hidden]){{display:none}}
    .info-panel-toggle{{background:none;border:1px solid var(--border);border-radius:6px;padding:4px 10px;font:inherit;font-size:.78rem;font-weight:600;color:var(--text-secondary);cursor:pointer}}
    .info-panel-toggle:hover{{color:var(--text);border-color:var(--border-strong)}}
    .info-panel-toggle[hidden]{{display:none}}
    .info-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:18px 20px}}
    .info-card h2{{margin:0 0 10px;font-size:.7em;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--faint)}}
    .info-panel-slot{{position:relative;flex:1;min-height:0;display:flex;flex-direction:column}}
    .info-stack{{display:flex;flex-direction:column;gap:16px;flex:1;min-height:0;overflow-y:auto}}
    .info-stack.is-covered{{visibility:hidden;pointer-events:none}}
    .spec-chat-panel[hidden]{{display:none!important}}
    .spec-chat-panel{{position:absolute;inset:0;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:0;display:flex;flex-direction:column;overflow:hidden;min-height:0}}
    .spec-chat-panel h2{{margin:0;padding:14px 16px 10px;font-size:.7em;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--faint)}}
    .spec-chat-log{{flex:1;overflow-y:auto;padding:4px 16px 16px;display:flex;flex-direction:column;gap:10px;min-height:0}}
    .spec-chat-log:empty::before{{content:"No messages yet.";color:var(--faint);font-size:.84rem}}
    .spec-chat-msg{{font-size:.875rem;line-height:1.45}}
    .spec-chat-who{{font-weight:600;margin-right:.35em}}
    .spec-chat-msg.is-human .spec-chat-who{{color:var(--ok)}}
    .spec-chat-msg.is-agent .spec-chat-who{{color:var(--accent,#6b8afd)}}
    .spec-chat-who::after{{content:":";font-weight:600}}
    .spec-chat-text{{color:var(--text-secondary);white-space:pre-wrap;word-break:break-word}}
    .meta-grid{{display:grid;grid-template-columns:minmax(5.5rem,42%) minmax(5rem,1fr);gap:6px 12px;font-size:.86em;line-height:1.45}}
    .meta-grid dt{{color:var(--faint);margin:0;overflow-wrap:break-word;word-break:normal;min-width:0}}
    .meta-grid dd{{margin:0;color:var(--text-secondary);overflow-wrap:break-word;word-break:normal;min-width:0}}
    .meta-grid > [hidden]{{display:none!important}}
    .quality-pending{{color:var(--faint);font-style:italic}}
    #state-result{{font-weight:700}}
    .export-links{{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin-top:14px;padding-top:12px;border-top:1px solid var(--row);font-size:.84em}}
    .export-link,.export-links a{{background:none;border:none;padding:0;font:inherit;color:var(--link);cursor:pointer;text-decoration:underline;text-underline-offset:2px}}
    .export-link:hover,.export-links a:hover{{opacity:.85}}
    .export-sep{{color:var(--faint);user-select:none}}
    .export-hint{{font-size:.9em;color:var(--faint);min-height:1.2em}}
    .board-col{{display:flex;justify-content:center}}
    .board-stack{{display:inline-flex;flex-direction:column;border:1px solid var(--border-strong);border-radius:10px;overflow:hidden;background:var(--surface);box-shadow:0 1px 4px var(--shadow,rgba(0,0,0,.06))}}
    .board-label{{padding:11px 16px;text-align:center;font-size:.93em;font-weight:600;background:var(--bg-elevated);color:var(--text)}}
    .board-label.black{{border-bottom:1px solid var(--border)}}
    .board-label.white{{border-top:1px solid var(--border)}}
    .board-label .sub{{display:block;font-size:.76em;font-weight:400;color:var(--faint);margin-top:3px}}
    .board-row{{display:flex;align-items:stretch}}
    .eval-col-v{{display:flex;flex-direction:column;align-items:center;flex-shrink:0;border-right:1px solid var(--border);background:var(--bg-elevated);padding:0}}
    .eval-track-v{{width:18px;background:var(--surface);position:relative;flex-shrink:0;border:1px solid var(--border-strong);border-radius:2px;flex:1;min-height:120px;margin:0}}
    .eval-black{{position:absolute;top:0;left:0;right:0;background:var(--text);transition:height .5s ease}}
    .spec-board-wrap{{display:block;background:var(--surface);width:min(600px,calc(100vh - 220px),calc(100vw - 848px));aspect-ratio:1;position:relative;overflow:hidden}}
    .spec-board-wrap .cm-chessboard,.spec-board{{width:100%;height:100%}}
    .moves-col{{display:flex;flex-direction:column;min-height:0;max-height:calc(100vh - 140px)}}
    .moves-col .panel{{background:var(--surface);border:1px solid var(--border);border-radius:8px;display:flex;flex-direction:column;flex:1;min-height:200px;overflow:hidden}}
    .moves-col .panel h2{{padding:14px 16px 0;margin:0}}
    .moves-scroll{{overflow-y:auto;flex:1;padding:8px 12px 14px}}
    .move-row{{display:grid;grid-template-columns:26px 1fr 1fr;gap:8px;padding:7px 4px;font-size:.88em;border-bottom:1px solid var(--row)}}
    .move-row:last-child{{border-bottom:none}}
    .move-row .mn{{color:var(--faint);text-align:right;font-size:.82em}}
    .move-row .w,.move-row .b{{cursor:pointer;border-radius:3px;padding:2px 4px;min-height:1.2em}}
    .move-row .w:empty,.move-row .b:empty{{cursor:default;pointer-events:none}}
    .move-row .w.on,.move-row .b.on{{font-weight:700;background:var(--row)}}
    @media(max-width:960px){{
      .layout{{grid-template-columns:1fr;gap:20px;width:100%;justify-content:stretch}}
      .moves-col{{max-height:320px}}
      .spec-board-wrap{{width:100%;max-width:480px}}
    }}
    </style></head><body class="game-view" data-game-id="{gid}">
    <div class="wrap">
    {PUBLIC_SITE_HEADER}
    <main>
    <div class="layout">
      <aside class="col info-col">
        <div class="info-col-head">
          <button type="button" class="info-panel-toggle" id="info-panel-toggle" hidden>Show chat</button>
        </div>
        <div class="info-panel-slot" id="info-panel-slot">
          <div class="info-stack" id="info-stack">
            <div class="info-card">
              <h2>Game info</h2>
              <dl class="meta-grid" id="meta"></dl>
              <div class="export-links">
                <a href="/g/{gid}/board.png" download="{gid}-board.png">Download board PNG</a>
                <span class="export-sep" aria-hidden="true">·</span>
                <button type="button" class="export-link" id="copy-pgn">Copy PGN</button>
                <span class="export-hint" id="action-hint"></span>
              </div>
            </div>
            <div class="info-card">
              <h2>Game state</h2>
              <dl class="meta-grid" id="state-meta">
                <dt>Result</dt><dd id="state-result">—</dd>
                <dt>Termination</dt><dd id="state-termination">—</dd>
                <dt id="state-eval-label">Evaluation</dt><dd id="state-eval">—</dd>
                <dt id="state-elo-label">ELO change</dt><dd id="state-elo">—</dd>
                <dt id="state-acc-white-label" class="quality-row" hidden>White accuracy</dt><dd id="state-acc-white" class="quality-row" hidden>—</dd>
                <dt id="state-pr-white-label" class="quality-row" hidden title="Estimated strength from move accuracy — not ladder Elo.">White Performance</dt><dd id="state-pr-white" class="quality-row" hidden title="Estimated strength from move accuracy — not ladder Elo.">—</dd>
                <dt id="state-acc-black-label" class="quality-row" hidden>Black accuracy</dt><dd id="state-acc-black" class="quality-row" hidden>—</dd>
                <dt id="state-pr-black-label" class="quality-row" hidden title="Estimated strength from move accuracy — not ladder Elo.">Black Performance</dt><dd id="state-pr-black" class="quality-row" hidden title="Estimated strength from move accuracy — not ladder Elo.">—</dd>
              </dl>
            </div>
          </div>
          <div class="spec-chat-panel" id="spec-chat-panel" hidden>
            <h2>Chat</h2>
            <div class="spec-chat-log" id="spec-chat-log" role="log" aria-live="polite"></div>
          </div>
        </div>
      </aside>
      <div class="col board-col" id="board-col">
        <div class="board-stack">
          <div class="board-label black" id="lbl-black">Black</div>
          <div class="board-row">
            <div class="eval-col-v" id="eval-col">
              <div class="eval-track-v" id="eval-track"><div class="eval-black" id="eval-black" style="height:50%"></div></div>
            </div>
            <div class="spec-board-wrap" id="board-wrap">
              <div id="board" class="spec-board" role="img" aria-label="chess board"></div>
            </div>
          </div>
          <div class="board-label white" id="lbl-white">White</div>
        </div>
      </div>
      <aside class="col moves-col" id="moves-col">
        <div class="panel">
          <h2>Moves</h2>
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
    <script type="module" src="/js/spectator-game.js"></script>
    </body></html>"""
