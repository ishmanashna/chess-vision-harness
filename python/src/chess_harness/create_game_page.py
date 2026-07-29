"""Create Game spectator page — model picker, auto auth, agent prompt."""

from __future__ import annotations

import html
import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple

from .agent_brief import public_base_url, render_agent_brief
from .api_keys import ApiKeyStore
from .api_limits import AuthContext, get_limit_enforcer, key_fingerprint
from .commands import resolve_agent_color
from .game_service import GameService
from .ladder_display import (
    SPECTATOR_PAGE_CSS,
    THEME_INIT_SCRIPT,
    THEME_TOGGLE_SCRIPT,
    spectator_tabs,
)
from .models import ModelRegistry

__all__ = ["render_create_game_page", "handle_create_game_post"]

_CREATE_CSS = """
    .form-card{max-width:520px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:18px 20px;margin-top:8px}
    .form-row{margin:0 0 14px}
    .form-row label{display:block;font-size:.85em;font-weight:600;color:var(--muted);margin-bottom:4px}
    .form-row select{width:100%;box-sizing:border-box;font-size:.9em;padding:8px 10px;border:1px solid var(--input-border);border-radius:4px;background:var(--input-bg);color:var(--text)}
    .form-hint{font-size:.78em;color:var(--faint);margin-top:4px}
    .btn-primary{font-size:.9em;padding:8px 16px;border-radius:4px;border:1px solid var(--link);background:var(--link);color:#fff;font-weight:600;cursor:pointer}
    .btn-secondary{font-size:.85em;padding:6px 12px;border-radius:4px;border:1px solid var(--input-border);background:var(--surface);color:var(--text);cursor:pointer;margin-top:8px}
    .err{color:var(--warn);background:var(--err-bg);border:1px solid var(--err-border);padding:10px 12px;border-radius:6px;margin:12px 0;font-size:.88em}
    .ok-box{color:var(--ok);background:var(--ok-bg);border:1px solid var(--ok-border);padding:10px 12px;border-radius:6px;margin:12px 0;font-size:.88em}
    .ok-box a{color:var(--link)}
    .brief-wrap{margin-top:16px;max-width:720px}
    .brief-wrap textarea{width:100%;box-sizing:border-box;min-height:320px;font-family:ui-monospace,monospace;font-size:.78em;padding:12px;border:1px solid var(--border);border-radius:6px;background:var(--bg-elevated);color:var(--text)}
    .game-id{font-size:1.05em;margin:8px 0}
"""


def _new_game_id() -> str:
    return f"game-{os.getpid()}-{random.randint(1000, 9999)}"


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def _model_options(models: List[Dict[str, Any]], selected: str = "") -> str:
    if not models:
        return '<option value="">— no inscribed models —</option>'
    opts = ['<option value="">Select model…</option>']
    for m in models:
        mid = m["id"]
        name = m.get("name", mid)
        label = name if name != mid else mid
        sel = " selected" if mid == selected else ""
        opts.append(f'<option value="{_esc(mid)}"{sel}>{_esc(label)} ({_esc(mid)})</option>')
    return "".join(opts)


def render_create_game_page(
    *,
    error: Optional[str] = None,
    success_game_id: Optional[str] = None,
    brief: Optional[str] = None,
    form: Optional[Dict[str, str]] = None,
) -> str:
    form = form or {}
    registry = ModelRegistry()
    models = [m for m in registry.list_models() if m.get("enabled", True)]
    no_models = not models

    parts: List[str] = []
    if error:
        parts.append(f'<div class="err">{_esc(error)}</div>')

    if success_game_id and brief:
        parts.extend([
            '<div class="ok-box">Game created. '
            f'<a href="/g/{_esc(success_game_id)}">Spectate this game</a>'
            ' · <a href="/spectator/">Spectator</a></div>',
            f'<p class="game-id">Game ID: <code>{_esc(success_game_id)}</code></p>',
            '<div class="brief-wrap">',
            '<label for="brief"><strong>Agent prompt</strong> — paste into your agent</label>',
            f'<textarea id="brief" readonly>{_esc(brief)}</textarea>',
            '<button type="button" class="btn-secondary" onclick="copyBrief()">Copy prompt</button>',
            "</div>",
        ])

    inscribe_hint = (
        "<p class='form-hint'>Inscribe first: <code>chess-harness models inscribe &lt;id&gt;</code></p>"
        if no_models
        else ""
    )
    parts.append(f"""
    <form class="form-card" method="post" action="/create">
      <div class="form-row">
        <label for="model_id">Model</label>
        <select id="model_id" name="model_id" required{" disabled" if no_models else ""}>
          {_model_options(models, form.get("model_id", ""))}
        </select>
        {inscribe_hint}
      </div>
      <button type="submit" class="btn-primary"{" disabled" if no_models else ""}>Create game</button>
    </form>
    """)

    copy_js = """
    function copyBrief(){
      const ta=document.getElementById('brief');
      if(!ta)return;
      ta.select();
      navigator.clipboard.writeText(ta.value).catch(()=>{document.execCommand('copy');});
    }
    """

    return f"""<!DOCTYPE html><html><head><title>Create Game · Chess Vision Harness</title>
    {THEME_INIT_SCRIPT}
    <style>
    {SPECTATOR_PAGE_CSS}
    {_CREATE_CSS}
    </style></head><body>
    <h1>Chess Vision Harness</h1>
    {spectator_tabs("create")}
    <p class="sub">Pick an inscribed model, create a rated game, and copy the agent prompt for HTTP play (<code>/api/v1</code>).</p>
    {"".join(parts)}
    <script>{copy_js}</script>
    {THEME_TOGGLE_SCRIPT}
    </body></html>"""


def handle_create_game_post(
    form: Dict[str, str],
    game_service: GameService,
    key_store: Optional[ApiKeyStore] = None,
) -> Tuple[str, Optional[str], Optional[str], Dict[str, str]]:
    """Mint key, create game with default matchmaking. Returns (html, game_id, brief, form_echo)."""
    store = key_store or ApiKeyStore()
    model_id = (form.get("model_id") or "").strip()
    echo = {"model_id": model_id}

    if not model_id:
        return render_create_game_page(error="Select a model.", form=echo), None, None, echo

    registry = ModelRegistry()
    if not registry.is_inscribed(model_id):
        return render_create_game_page(error=f"Unknown model '{model_id}'.", form=echo), None, None, echo

    api_key = store.create(model_id)
    auth = AuthContext(model_id=model_id, key_fingerprint=key_fingerprint(api_key))
    denied = get_limit_enforcer().check_create_game(game_service, auth)
    if denied is not None:
        detail = "Game creation limited; try again later."
        try:
            payload = json.loads(denied.body.decode("utf-8"))
            detail = str(payload.get("error") or detail)
        except Exception:
            pass
        return render_create_game_page(error=detail, form=echo), None, None, echo

    color = resolve_agent_color(None)
    game_id = _new_game_id()
    result = game_service.new_game(game_id, color, model_name=model_id, opponent_id=None)
    if not result.get("ok"):
        return (
            render_create_game_page(error=result.get("error", "Failed to create game"), form=echo),
            None,
            None,
            echo,
        )

    get_limit_enforcer().record_create_game(auth)
    brief = render_agent_brief(public_base_url(), game_id, api_key)
    html_out = render_create_game_page(success_game_id=game_id, brief=brief, form=echo)
    return html_out, game_id, brief, echo
