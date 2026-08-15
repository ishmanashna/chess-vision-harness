"""Shared agent + opponent ladder formatting for CLI and spectator."""

from __future__ import annotations

import html
import os
from typing import List, Optional, Tuple

from .calibration_view import (
    merge_calibration_ratings,
    split_opponent_ladder_calibrated,
)
from .elo import ELOLadder
from .opponents import Opponent, OpponentCatalog, get_catalog

RATING_SOURCE_LABELS = {
    "ccrl": "CCRL",
    "stockfish_uci": "Stockfish UCI",
    "stockfish_harness": "Stockfish harness",
    "inverse_sf": "Inverse Stockfish",
    "uci_harness": "UCI harness",
    "builtin": "Built-in",
}


def rating_source_label(source: str) -> str:
    return RATING_SOURCE_LABELS.get(source, source)


def opponent_status(catalog: OpponentCatalog, opp: Opponent) -> str:
    if not opp.enabled:
        return "disabled"
    return "ready" if catalog._is_playable(opp) else "missing"


def split_opponent_ladder(
    catalog: OpponentCatalog,
) -> Tuple[List[Opponent], List[Opponent]]:
    """Legacy split — prefer split_opponent_ladder_calibrated."""
    floating_types = ("uci", "uci_elo", "uci_harness", "stockfish_harness", "inverse_sf", "random")
    sub1320 = sorted(
        [o for o in catalog.list_opponents() if o.enabled and o.type in floating_types],
        key=lambda o: o.elo,
    )
    stockfish = [o for o in catalog.list_opponents() if o.enabled and o.type == "stockfish"]
    return sub1320, stockfish


def _format_quality_cli_suffix(entry: dict) -> str:
    acc = entry.get("mean_accuracy")
    pr = entry.get("mean_play_rating")
    if acc is None and pr is None:
        return ""
    parts = []
    if acc is not None:
        parts.append(f"acc {acc}%")
    if pr is not None:
        parts.append(f"performance {round(pr)}")
    qg = int(entry.get("quality_games", 0))
    if qg:
        parts.append(f"{qg} quality")
    return " — " + ", ".join(parts) if parts else ""


def format_agent_leaderboard_cli(ladder: ELOLadder) -> str:
    board = ladder.get_leaderboard()
    if not board:
        return "No inscribed models. Run: chess-harness models list"
    lines = ["Agent rankings:"]
    for i, entry in enumerate(board, 1):
        label = entry["name"] if entry.get("name") != entry["model"] else entry["model"]
        games = entry.get("games", 0)
        g = f"{games} game" + ("" if games == 1 else "s")
        disabled = "" if entry.get("enabled", True) else " [disabled]"
        quality = _format_quality_cli_suffix(entry)
        lines.append(
            f"  {i}. {label} ({entry['model']}): {entry['elo']} ELO — {g}{quality}{disabled}"
        )
    return "\n".join(lines)


def format_opponent_ladder_cli(catalog: OpponentCatalog | None = None) -> str:
    cat = catalog or get_catalog()
    calibration = merge_calibration_ratings()
    engines, harness, anchors = split_opponent_ladder_calibrated(cat, calibration)

    lines = ["", "Opponent ladder (calibrated ELO where available):"]
    lines.append("  Other engines (MinimalChess, random):")
    for opp, cal_elo, games in engines:
        status = opponent_status(cat, opp)
        elo_txt = f"{cal_elo}*" if games == 0 and opp.type != "stockfish" else str(cal_elo)
        g = f", {games} cal games" if games else ""
        lines.append(
            f"    {opp.id}: {elo_txt} ELO{g} "
            f"[{rating_source_label(opp.rating_source)}, {status}]"
        )
    lines.append("  Stockfish handicaps (skill 0, calibrated):")
    for opp, cal_elo, games in harness:
        status = opponent_status(cat, opp)
        elo_txt = f"{cal_elo}*" if games == 0 else str(cal_elo)
        g = f", {games} cal games" if games else ""
        lines.append(
            f"    {opp.id}: {elo_txt} ELO{g} "
            f"[{rating_source_label(opp.rating_source)}, {status}]"
        )
    lines.append("  Stockfish anchors (fixed UCI ELO):")
    for opp, elo, _ in anchors[:5]:
        lines.append(f"    {opp.id}: {elo} ELO")
    if len(anchors) > 5:
        lines.append(f"    ... {len(anchors) - 5} more stockfish tiers")
    return "\n".join(lines)


def render_leaderboard_html(ladder: ELOLadder) -> str:
    catalog = get_catalog()
    board = ladder.get_leaderboard()
    calibration = merge_calibration_ratings()
    engines, harness, anchors = split_opponent_ladder_calibrated(catalog, calibration)

    agent_rows = ""
    for i, entry in enumerate(board, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else str(i)
        agent_rows += (
            f"<tr><td>{medal}</td>"
            f"<td>{entry.get('name', entry['model'])}</td>"
            f"<td><code>{entry['model']}</code></td>"
            f"<td>{entry['elo']}</td>"
            f"<td>{entry.get('games', 0)}</td></tr>"
        )

    def floating_row(opp: Opponent, cal_elo: Optional[int], games: int) -> str:
        status_key = opponent_status(catalog, opp)
        if status_key == "ready":
            status = '<span class="ok">ready</span>'
        elif status_key == "disabled":
            status = '<span class="miss">disabled</span>'
        else:
            status = '<span class="miss">missing</span>'
        uncalibrated = games == 0 and opp.type != "stockfish"
        display = f"{cal_elo}*" if uncalibrated else str(cal_elo)
        catalog_note = (
            f'<span class="catalog">{opp.elo}</span>'
            if games > 0 and cal_elo != opp.elo
            else ""
        )
        return (
            f'<tr data-opp-id="{opp.id}"><td><code>{opp.id}</code></td>'
            f'<td>{opp.display_name}</td>'
            f'<td class="cal-elo"><strong>{display}</strong></td>'
            f'<td>{catalog_note}</td>'
            f'<td class="cal-games">{games}</td>'
            f"<td>{rating_source_label(opp.rating_source)}</td>"
            f"<td>{status}</td></tr>"
        )

    def anchor_row(opp: Opponent, elo: int) -> str:
        return (
            f"<tr><td><code>{opp.id}</code></td>"
            f"<td>{opp.display_name}</td>"
            f"<td><strong>{elo}</strong></td>"
            f"<td class='catalog'>anchor</td>"
            f"<td>—</td>"
            f"<td>{rating_source_label(opp.rating_source)}</td>"
            f"<td><span class='ok'>ready</span></td></tr>"
        )

    engine_rows = "".join(floating_row(o, e, g) for o, e, g in engines)
    harness_rows = "".join(floating_row(o, e, g) for o, e, g in harness)
    sf_rows = "".join(anchor_row(o, e) for o, e, _ in anchors)

    agent_block = (
        "<h2>Agent Rankings</h2>"
        "<table><tr><th>#</th><th>Model</th><th>ID</th><th>ELO</th><th>Games</th></tr>"
        + agent_rows
        + "</table>"
        if agent_rows
        else '<p class="empty">No inscribed models yet.</p>'
    )

    return f"""<!DOCTYPE html><html><head><title>ELO Ladder · Chess Vision Harness</title>
    {FAVICON_LINKS}
    {THEME_INIT_SCRIPT}
    <style>
    {SPECTATOR_PAGE_CSS}
    .catalog{{color:var(--faint);font-size:.85em}}
    </style></head><body>
    <h1>Chess Vision Harness</h1>
    {spectator_tabs("ladder")}
    {agent_block}
    <h2>Opponent Ladder — Calibrated</h2>
    <h3>Other engines (MinimalChess, random)</h3>
    <table><tr><th>ID</th><th>Name</th><th>Calibrated</th><th>Catalog</th><th>Cal games</th><th>Source</th><th>Status</th></tr>{engine_rows}</table>
    <h3>Stockfish handicaps (skill 0, calibrated)</h3>
    <table><tr><th>ID</th><th>Name</th><th>Calibrated</th><th>Catalog</th><th>Cal games</th><th>Source</th><th>Status</th></tr>{harness_rows}</table>
    <h3>Stockfish anchors (fixed UCI ELO)</h3>
    <table><tr><th>ID</th><th>Name</th><th>ELO</th><th>Catalog</th><th>Cal games</th><th>Source</th><th>Status</th></tr>{sf_rows}</table>
    <script>
    async function refreshLadder(){{
      try{{
        const r=await fetch('/api/calibration/status');
        const d=await r.json();
        const byId={{}};(d.rating_table||[]).forEach(row=>{{byId[row.id]=row;}});
        document.querySelectorAll('tr[data-opp-id]').forEach(tr=>{{
          const row=byId[tr.dataset.oppId];
          if(!row||row.anchor)return;
          const elo=tr.querySelector('.cal-elo');
          const games=tr.querySelector('.cal-games');
          if(elo)elo.innerHTML='<strong>'+row.elo+'</strong>';
          if(games)games.textContent=row.games||0;
        }});
      }}catch(e){{}}
    }}
    refreshLadder();setInterval(refreshLadder,2000);
    </script>
    {THEME_TOGGLE_SCRIPT}
    </body></html>"""


def _calibration_secret_meta(*, loopback: bool) -> str:
    if not loopback:
        return ""
    secret = os.environ.get("CHESS_HARNESS_CALIBRATION_SECRET", "").strip()
    if not secret:
        return ""
    return f'<meta name="calibration-secret" content="{html.escape(secret, quote=True)}"/>'


def render_calibration_html(*, loopback: bool = True) -> str:
    secret_panel = ""
    if not loopback:
        secret_panel = """
    <div class="cal-panel" id="cal-secret-panel">
      <h2>Calibration secret</h2>
      <p>This host is not loopback — POST actions need <code>CHESS_HARNESS_CALIBRATION_SECRET</code>. Paste it below (stored in this tab only, never embedded in the page).</p>
      <label for="cal-secret-input" class="sr-only">Calibration secret</label>
      <input type="password" id="cal-secret-input" class="cal-secret-input" autocomplete="off" placeholder="Paste calibration secret" oninput="saveCalSecret(this.value)"/>
    </div>"""
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
    <title>Calibration · Chess Vision Harness</title>
    {FAVICON_LINKS}
    {_calibration_secret_meta(loopback=loopback)}
    <meta name="calibration-loopback" content="{"1" if loopback else "0"}"/>
    {THEME_INIT_SCRIPT}
    <link rel="stylesheet" href="/css/site.css"/>
    <style>
    .cal-page h2{{margin:24px 0 8px;font-size:1.05rem}}
    .cal-lead{{margin:0 0 16px;color:var(--muted);font-size:.9rem;max-width:48rem;text-align:justify}}
    .cal-panel{{max-width:920px;margin:0 0 18px;padding:14px 16px;background:var(--surface);border:1px solid var(--border);border-radius:8px}}
    .cal-panel h2{{margin:0 0 6px;font-size:.72rem;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--faint)}}
    .cal-panel p{{margin:0;color:var(--text-secondary);font-size:.88rem;max-width:none}}
    .cal-panel .hint{{margin-top:6px;font-size:.8rem;color:var(--faint)}}
    .game-feed{{max-width:920px;border:1px solid var(--border);border-radius:8px;overflow:hidden;background:var(--surface)}}
    .game-line{{font-size:.85em;padding:8px 12px;border-bottom:1px solid var(--row)}}
    .game-line:last-child{{border-bottom:none}}
    .delta-up{{color:var(--ok)}}.delta-down{{color:var(--warn)}}
    .playing-badge{{color:var(--ok);font-weight:600;font-size:.85em}}
    .idle-badge{{color:var(--faint);font-size:.85em}}
    .cal-btn{{font-size:.8em;padding:4px 10px;border-radius:4px;border:1px solid var(--input-border,var(--border));background:var(--surface);color:var(--text);cursor:pointer;font-weight:600}}
    .cal-btn.start{{border-color:var(--link);color:var(--link)}}
    .cal-btn.stop{{border-color:var(--warn);color:var(--warn)}}
    .cal-btn:disabled{{opacity:.45;cursor:not-allowed}}
    .cal-controls{{display:flex;align-items:center;gap:6px;justify-content:flex-end}}
    .cal-par{{width:3em;padding:4px 6px;font-size:.85em;border:1px solid var(--input-border,var(--border));border-radius:4px;text-align:center;background:var(--input-bg,var(--surface));color:var(--text)}}
    .cal-par:disabled{{opacity:.6}}
    .status-meta{{margin:0 0 12px;color:var(--faint);font-size:.85em;min-height:1em}}
    .cal-error{{margin:0 0 12px;padding:10px 12px;border-radius:6px;border:1px solid var(--warn);background:var(--err-bg);color:var(--warn);font-size:.88em;display:none}}
    .cal-error.visible{{display:block}}
    .cal-secret-input{{width:min(420px,100%);padding:6px 8px;font-size:.88em;border:1px solid var(--input-border,var(--border));border-radius:4px;background:var(--input-bg,var(--surface));color:var(--text)}}
    .sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}
    .cal-toolbar{{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;margin:0 0 16px;padding:12px 14px;background:var(--surface);border:1px solid var(--border);border-radius:8px;max-width:920px}}
    .cal-toolbar label{{font-size:.85em;font-weight:600;color:var(--muted)}}
    .cal-toolbar select{{font-size:.85em;padding:5px 8px;border:1px solid var(--input-border,var(--border));border-radius:4px;background:var(--input-bg,var(--surface));color:var(--text)}}
    .cal-btn.primary{{border-color:var(--link);background:var(--link);color:#fff}}
    .cal-legend{{font-size:.8em;color:var(--faint);margin:0 0 8px;max-width:none;text-align:justify}}
    .cal-table-wrap{{max-width:1100px;overflow-x:auto}}
    table.cal-table{{border-collapse:collapse;width:100%;margin-top:6px;background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden}}
    table.cal-table th,table.cal-table td{{border-bottom:1px solid var(--row);padding:10px 12px;text-align:left;font-size:.88em}}
    table.cal-table th{{background:var(--bg-elevated);font-weight:600;color:var(--muted);white-space:nowrap}}
    table.cal-table tr:last-child td{{border-bottom:none}}
    table.cal-table .empty{{color:var(--faint)}}
    table.cal-table code{{font-size:.88em}}
    .catalog{{color:var(--faint)}}
    </style></head><body class="cal-page">
    <div class="wrap">
    {PUBLIC_SITE_HEADER}
    <h2>Engine calibration</h2>
    <p class="cal-lead">Results-only Elo for the ladder. Accuracy is mean move quality from continuous games. Performance maps move accuracy through the accuracy→Elo table — it is not ladder Elo. Rebuild the accuracy→Elo map after enough samples.</p>
    {secret_panel}
    <div class="cal-toolbar">
      <label for="pairing-mode">Opponent pairing</label>
      <select id="pairing-mode" onchange="onPairingModeChange(this.value)">
        <option value="floaters">Among floaters (ELO-weighted)</option>
        <option value="random">Random (any opponent)</option>
        <option value="anchors">Only vs Stockfish anchors</option>
        <option value="anchors-self">Anchors among themselves</option>
        <option value="fixed">Fixed opponent</option>
      </select>
      <label for="fixed-opponent">Play against</label>
      <select id="fixed-opponent" disabled onchange="setFixedOpponent(this.value)"></select>
      <button type="button" class="cal-btn primary" id="start-all-btn" onclick="startAllEngines(this)">Start all (1 each)</button>
      <button type="button" class="cal-btn stop" id="stop-all-btn" onclick="stopAllEngines(this)">Stop all</button>
      <button type="button" class="cal-btn" id="rebuild-play-rating-btn" onclick="rebuildPlayRatingMap(this)">Rebuild accuracy→Elo table</button>
    </div>
    <div id="cal-error" class="cal-error" role="alert"></div>
    <div id="status-meta" class="status-meta"></div>
    <div class="cal-panel" id="play-rating-panel">
      <h2>Quality samples &amp; accuracy→Elo map</h2>
      <p id="play-rating-summary">Loading…</p>
    </div>
    <h2>Calibrated ratings</h2>
    <p class="cal-legend">Elo = results only · Accuracy = mean move accuracy · Performance = accuracy→Elo map (not ladder Elo).</p>
    <div class="cal-table-wrap">
    <table class="cal-table" id="rating-table"><tr><th>ID</th><th>Calibrated Elo</th><th>Games</th><th>Accuracy</th><th title="Performance from move accuracy via the accuracy→Elo table — not ladder Elo.">Performance</th><th>Activity</th><th></th></tr>
    <tr><td colspan="7" class="empty">No calibration data yet.</td></tr></table>
    </div>
    <h2>Recent games</h2>
    <p class="cal-legend">Green = Elo gain · Orange = Elo loss (per engine updated after that game)</p>
    <div id="game-feed" class="game-feed"></div>
    </div>
    <script>
    function esc(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}}
    function parSlug(id){{return String(id).replace(/[^a-zA-Z0-9_-]/g,'-');}}
    function parFieldId(id){{return 'cal-par-'+parSlug(id);}}
    function fmtAcc(v,std){{
      if(v==null||v==='')return '—';
      const base=Number(v).toFixed(1)+'%';
      if(std==null||std==='')return base;
      return base+' ± '+Number(std).toFixed(1);
    }}
    function fmtPlayRating(v){{
      if(v==null||v==='')return '—';
      return String(Math.round(Number(v)));
    }}
    let calState={{pairingLocked:false,confirmAbove:4,hardCap:16,fleetBudget:4,fleetConfirmAbove:4,fleetInUse:0,lastPairingMode:'floaters'}};
    function showCalError(msg){{
      const el=document.getElementById('cal-error');
      if(!el)return;
      if(!msg){{el.textContent='';el.classList.remove('visible');return;}}
      el.textContent=msg;
      el.classList.add('visible');
    }}
    function saveCalSecret(value){{
      try{{sessionStorage.setItem('chess-harness-cal-secret',value||'');}}catch(e){{}}
    }}
    (function initCalSecretInput(){{
      const inp=document.getElementById('cal-secret-input');
      if(!inp)return;
      try{{
        const saved=sessionStorage.getItem('chess-harness-cal-secret');
        if(saved)inp.value=saved;
      }}catch(e){{}}
    }})();
    function calHeaders(){{
      const headers={{}};
      const meta=document.querySelector('meta[name="calibration-secret"]');
      if(meta&&meta.content){{headers['CHESS_HARNESS_CALIBRATION_SECRET']=meta.content;return headers;}}
      try{{
        const saved=sessionStorage.getItem('chess-harness-cal-secret');
        if(saved)headers['CHESS_HARNESS_CALIBRATION_SECRET']=saved;
      }}catch(e){{}}
      return headers;
    }}
    async function calPost(url){{
      const r=await fetch(url,{{method:'POST',headers:calHeaders()}});
      if(!r.ok){{
        let msg=r.status+' '+r.statusText;
        try{{
          const d=await r.json();
          msg=(d&&d.detail)?(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail)):msg;
        }}catch(e){{}}
        showCalError(msg);
        throw new Error(msg);
      }}
      showCalError('');
      return r;
    }}
    function readParallel(id){{
      const inp=document.querySelector('input.cal-par[data-eid="'+id+'"]');
      const n=parseInt(inp&&inp.value?inp.value:'1',10);
      const cap=calState.hardCap||16;
      return Math.max(1,Math.min(cap,isNaN(n)?1:n));
    }}
    function savedParallel(id,fallback){{
      const inp=document.querySelector('input.cal-par[data-eid="'+id+'"]');
      if(inp&&!inp.disabled&&inp.value)return inp.value;
      return String(fallback);
    }}
    function setPairingControlsLocked(locked){{
      calState.pairingLocked=!!locked;
      const modeSel=document.getElementById('pairing-mode');
      const fixSel=document.getElementById('fixed-opponent');
      if(modeSel)modeSel.disabled=locked;
      if(fixSel)fixSel.disabled=locked||(modeSel&&modeSel.value!=='fixed');
    }}
    async function setPairingMode(mode){{
      await calPost('/api/calibration/pairing-mode?mode='+encodeURIComponent(mode));
      calState.lastPairingMode=mode;
    }}
    function onPairingModeChange(mode){{
      if(calState.pairingLocked){{
        showCalError('Stop continuous calibration before changing pairing settings.');
        const modeSel=document.getElementById('pairing-mode');
        if(modeSel)modeSel.value=calState.lastPairingMode||'floaters';
        return;
      }}
      const fix=document.getElementById('fixed-opponent');
      if(fix)fix.disabled=(mode!=='fixed');
      setPairingMode(mode).catch(()=>{{}});
    }}
    async function setFixedOpponent(opponent){{
      if(!opponent||calState.pairingLocked)return;
      await calPost('/api/calibration/fixed-opponent?opponent='+encodeURIComponent(opponent));
    }}
    async function startAllEngines(btn){{
      const parallel=1;
      const engines=(calState.calibratableEngines||[]).length;
      const fleetBudget=calState.fleetBudget||4;
      const fleetInUse=calState.fleetInUse||0;
      const projected=fleetInUse+engines*parallel;
      if(projected>fleetBudget){{
        showCalError('Start all would exceed fleet parallel cap ('+fleetBudget+'); projected '+projected+' — stop engines or reduce parallel.');
        return;
      }}
      const msg='Start continuous calibration for all eligible engines ('+engines+' × '+parallel+' parallel each, fleet cap '+fleetBudget+')? This can spawn many engine processes.';
      if(!window.confirm(msg))return;
      if(btn)btn.disabled=true;
      try{{
        await calPost('/api/calibration/start-all?parallel='+parallel+'&confirm=1');
      }}catch(e){{}}finally{{
        if(btn)btn.disabled=false;
        refreshFull();
        refreshLive();
      }}
    }}
    async function stopAllEngines(btn){{
      if(btn){{btn.disabled=true;btn.textContent='Stopping…';}}
      try{{
        const ctrl=new AbortController();
        const t=setTimeout(()=>ctrl.abort(),120000);
        try{{
          const r=await fetch('/api/calibration/stop-all',{{method:'POST',headers:calHeaders(),signal:ctrl.signal}});
          if(!r.ok){{await calPost('/api/calibration/stop-all');}}
          else showCalError('');
        }}finally{{clearTimeout(t);}}
      }}catch(e){{showCalError(e&&e.message?e.message:'Stop failed');}}
      finally{{
        if(btn){{btn.disabled=false;btn.textContent='Stop all';}}
        refreshFull();
        refreshLive();
      }}
    }}
    async function rebuildPlayRatingMap(btn){{
      if(!window.confirm('Rebuild the accuracy→Elo table from collected quality samples? This may take a minute and updates Performance on the leaderboard.'))return;
      if(btn){{btn.disabled=true;btn.textContent='Rebuilding…';}}
      const meta=document.getElementById('status-meta');
      if(meta)meta.textContent='Rebuilding accuracy→Elo table…';
      try{{
        const r=await calPost('/api/calibration/rebuild-play-rating-map');
        const d=await r.json();
        const rows=d.rows_recomputed!=null?d.rows_recomputed:'?';
        if(meta)meta.textContent='Rebuild complete — '+rows+' finished-game Performance rows updated.';
      }}catch(e){{}}finally{{
        if(btn){{btn.disabled=false;btn.textContent='Rebuild accuracy→Elo table';}}
        refreshFull();
        refreshLive();
      }}
    }}
    async function setContinuous(id,start,btn){{
      if(start){{
        const parallel=readParallel(id);
        if(parallel>calState.confirmAbove){{
          const msg='Start '+id+' with '+parallel+' parallel games? High parallel load can slow the PC.';
          if(!window.confirm(msg))return;
        }}
      }}
      if(btn)btn.disabled=true;
      let path='/api/calibration/continuous/'+encodeURIComponent(id)+(start?'/start':'/stop');
      if(start){{
        const parallel=readParallel(id);
        path+='?parallel='+parallel;
        if(parallel>calState.confirmAbove)path+='&confirm=1';
      }}
      try{{
        await calPost(path);
      }}catch(e){{}}finally{{
        if(btn)btn.disabled=false;
        refreshFull();
        refreshLive();
      }}
    }}
    function renderGameFeed(games){{
      const feed=document.getElementById('game-feed');
      if(!feed)return;
      const list=(games||[]).slice().reverse();
      feed.innerHTML=list.length?list.map(g=>{{
        let upd='';
        (g.updates||[]).forEach(u=>{{
          const cls=u.elo_delta>=0?'delta-up':'delta-down';
          const sign=u.elo_delta>=0?'+':'';
          upd+=` <span class="${{cls}}">${{esc(u.opponent_id)}} ${{u.elo_before}}→${{u.elo_after}} (${{sign}}${{u.elo_delta.toFixed(1)}})</span>`;
        }});
        const skip=g.skipped?' <span class="idle-badge">(no Elo change)</span>':'';
        return `<div class="game-line">#${{g.game_index||'?'}} <strong>${{esc(g.white)}}</strong> vs <strong>${{esc(g.black)}}</strong> → ${{esc(g.result)}}${{skip}}${{upd}}</div>`;
      }}).join(''):'<p class="empty">No games logged yet.</p>';
    }}
    function applyLiveStatus(d){{
      if(d.parallel_confirm_above!=null)calState.confirmAbove=d.parallel_confirm_above;
      if(d.parallel_hard_cap!=null)calState.hardCap=d.parallel_hard_cap;
      if(d.fleet_parallel_hard_cap!=null)calState.fleetBudget=d.fleet_parallel_hard_cap;
      if(d.fleet_parallel_confirm_above!=null)calState.fleetConfirmAbove=d.fleet_parallel_confirm_above;
      if(d.fleet_parallel_in_use!=null)calState.fleetInUse=d.fleet_parallel_in_use;
      if(d.calibratable_engines)calState.calibratableEngines=d.calibratable_engines;
      if(d.pairing_mode)calState.lastPairingMode=d.pairing_mode;
      setPairingControlsLocked(d.pairing_locked||d.active);
      let meta='';
      if(d.pairing_mode)meta+='Pairing: '+d.pairing_mode;
      if(d.pairing_mode==='fixed'&&d.fixed_opponent_id)meta+=(meta?' · ':'')+'vs '+d.fixed_opponent_id;
      if(d.pairing_locked)meta+=(meta?' · ':'')+'pairing locked while running';
      if(d.in_progress)meta+=(meta?' · ':'')+d.in_progress+' games in flight';
      if(calState.fleetBudget)meta+=(meta?' · ':'')+'fleet parallel '+calState.fleetInUse+'/'+calState.fleetBudget;
      if(d.calibration_worker_ok===false){{
        const werr=d.calibration_worker_error||'calibration worker unreachable';
        showCalError('Calibration worker down: '+werr);
      }}
      if(d.skipped_games)meta+=(meta?' · ':'')+d.skipped_games+' games skipped (timeout)';
      const metaEl=document.getElementById('status-meta');
      if(metaEl&&!metaEl.textContent.startsWith('Rebuilding')&&!metaEl.textContent.startsWith('Rebuild complete'))metaEl.textContent=meta;
      renderGameFeed(d.recent_games);
    }}
    async function refreshLive(){{
      try{{
        const r=await fetch('/api/calibration/status/live');
        if(!r.ok){{
          showCalError('Live status unavailable ('+r.status+' '+r.statusText+').');
          return;
        }}
        const d=await r.json();
        applyLiveStatus(d);
      }}catch(e){{
        showCalError('Live status poll failed: '+(e&&e.message?e.message:'unknown error'));
      }}
    }}
    async function refreshFull(){{
      const prEl=document.getElementById('play-rating-summary');
      try{{
        const r=await fetch('/api/calibration/status');
        if(!r.ok){{
          const msg='Calibration status unavailable ('+r.status+' '+r.statusText+').';
          showCalError(msg);
          if(prEl)prEl.textContent=msg;
          return;
        }}
        const d=await r.json();
        applyLiveStatus(d);
        const pr=d.play_rating||{{}};
        const prm=d.play_rating_map||{{}};
        if(prEl){{
          const n=pr.sample_count||0;
          const need=pr.min_samples||30;
          let lines=[];
          if(n>0){{
            lines.push('Quality samples: '+n+(n<need?' / '+need+' collecting':' collected'));
          }}else{{
            lines.push('No quality samples yet. Eligible floaters (101+ Elo games) append samples after each continuous game.');
          }}
          const sampleCount=prm.sample_count||0;
          const minSamples=prm.min_samples||30;
          if(prm.warm){{
            lines.push('Accuracy→Elo map: warm — '+sampleCount+' engine pairs'+(prm.fitted_at?' · '+prm.fitted_at:''));
          }}else{{
            lines.push('Accuracy→Elo map: need '+minSamples+' engine pairs (have '+sampleCount+').');
          }}
          prEl.textContent=lines.join(' · ');
        }}
        const modeSel=document.getElementById('pairing-mode');
        if(modeSel&&d.pairing_mode&&!calState.pairingLocked){{
          modeSel.value=d.pairing_mode;
          calState.lastPairingMode=d.pairing_mode;
          const fix=document.getElementById('fixed-opponent');
          if(fix)fix.disabled=(d.pairing_mode!=='fixed');
        }}
        const fixSel=document.getElementById('fixed-opponent');
        if(fixSel&&(d.pairing_opponents||[]).length){{
          const cur=fixSel.value||d.fixed_opponent_id||'';
          fixSel.innerHTML=(d.pairing_opponents||[]).map(o=>'<option value="'+esc(o.id)+'">'+esc(o.id)+'</option>').join('');
          if(cur)fixSel.value=cur;
        }}
        const rt=document.getElementById('rating-table');
        const hardCap=calState.hardCap||16;
        const rows=(d.rating_table||[]).map(row=>{{
          const elo=row.uncalibrated?`<span class="catalog">${{row.elo}}*</span>`:`<strong>${{row.elo}}</strong>`;
          const acc=fmtAcc(row.mean_accuracy,row.accuracy_std);
          const est=fmtPlayRating(row.play_rating);
          let activity='<span class="idle-badge">—</span>';
          if(row.continuous){{
            const live=row.playing||0;
            if(live>0){{
              activity=`<span class="playing-badge">${{live}} live</span>`;
            }}else{{
              activity='<span class="playing-badge">waiting</span>';
            }}
          }}else if(row.activity==='disabled'||row.enabled===false){{
            activity='<span class="idle-badge">disabled</span>';
          }}
          let ctrl='';
          if(row.can_calibrate){{
            const parVal=row.continuous?String(row.parallel||1):savedParallel(row.id,1);
            const parDisabled=row.continuous?' disabled':'';
            const parId=parFieldId(row.id);
            const parInput=`<input class="cal-par" id="${{esc(parId)}}" name="${{esc(parId)}}" type="number" min="1" max="${{hardCap}}" value="${{parVal}}" data-eid="${{esc(row.id)}}"${{parDisabled}} title="Parallel games (max ${{hardCap}})">`;
            if(row.continuous){{
              ctrl=`<div class="cal-controls">${{parInput}}<button type="button" class="cal-btn stop" data-eid="${{esc(row.id)}}" onclick="setContinuous(this.getAttribute('data-eid'),false,this)">Stop</button></div>`;
            }}else{{
              ctrl=`<div class="cal-controls">${{parInput}}<button type="button" class="cal-btn start" data-eid="${{esc(row.id)}}" onclick="setContinuous(this.getAttribute('data-eid'),true,this)">Start</button></div>`;
            }}
          }}
          return `<tr><td><code>${{esc(row.id)}}</code></td><td>${{elo}}</td><td>${{row.games||0}}</td><td title="Mean accuracy from quality samples">${{acc}}</td><td title="Performance from move accuracy via the accuracy→Elo table; not ladder Elo">${{est}}</td><td>${{activity}}</td><td>${{ctrl}}</td></tr>`;
        }}).join('');
        rt.innerHTML='<tr><th>ID</th><th>Calibrated Elo</th><th>Games</th><th>Accuracy</th><th title="Performance from move accuracy via the accuracy→Elo table — not ladder Elo.">Performance</th><th>Activity</th><th></th></tr>'
          +(rows||'<tr><td colspan="7" class="empty">No ratings yet.</td></tr>');
      }}catch(e){{
        const msg='Calibration status failed: '+(e&&e.message?e.message:'unknown error');
        showCalError(msg);
        if(prEl)prEl.textContent=msg;
      }}
    }}
    refreshFull();
    refreshLive();
    setInterval(refreshLive,2500);
    setInterval(refreshFull,30000);
    </script>
    <script src="/js/common.js" defer></script>
    </body></html>"""


THEME_INIT_SCRIPT = """<script>(function(){try{var t=localStorage.getItem('chess-harness-theme');if(t!=='dark'&&t!=='light'){t=matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'}document.documentElement.setAttribute('data-theme',t)}catch(e){}})();</script>"""

FAVICON_LINKS = """<link rel="icon" href="/favicon.ico" sizes="any"/>
  <link rel="icon" href="/favicon.svg" type="image/svg+xml"/>"""

THEME_TOGGLE_SCRIPT = """
<script>
(function(){
  function current(){return document.documentElement.getAttribute('data-theme')==='dark'?'dark':'light'}
  function apply(t){
    document.documentElement.setAttribute('data-theme',t);
    try{localStorage.setItem('chess-harness-theme',t)}catch(e){}
    document.querySelectorAll('[data-theme-toggle]').forEach(function(btn){
      btn.textContent=t==='dark'?'Light mode':'Dark mode';
      btn.setAttribute('aria-label',t==='dark'?'Switch to light mode':'Switch to dark mode');
    });
  }
  document.querySelectorAll('[data-theme-toggle]').forEach(function(btn){
    btn.addEventListener('click',function(){apply(current()==='dark'?'light':'dark')});
  });
  apply(current());
})();
</script>
"""

PUBLIC_SITE_HEADER = """
  <header class="site-header">
    <div class="header-top">
      <div class="header-brand">
        <h1 class="site-title">Chess Vision Harness</h1>
      </div>
      <nav class="site-nav" aria-label="Main">
        <a href="/" id="nav-home">Home</a>
        <a href="/launch/?flow=engine" id="nav-create">Create Game</a>
        <a href="/spectator/" id="nav-spectator">Spectator</a>
        <a href="/leaderboard/" id="nav-leaderboard">Leaderboard</a>
        <a href="/contact/" id="nav-contact">Contact</a>
      </nav>
      <div class="header-controls">
        <button type="button" class="theme-toggle" data-theme-toggle>Dark mode</button>
        <span class="status-chip" data-status-chip data-state="sleeping" title="Checking server status…">
          <span class="status-dot" aria-hidden="true"></span>
          <span data-status-label>Sleeping</span>
        </span>
      </div>
    </div>
  </header>
"""

NAV = (
    '<a class="back" href="/spectator/">&larr; Spectator</a> &nbsp;|&nbsp; '
    '<a class="back" href="/calibration">Calibration</a> &nbsp;|&nbsp; '
    '<a class="back" href="/leaderboard">ELO Ladder</a> &nbsp;|&nbsp; '
    '<button type="button" class="theme-toggle theme-toggle-inline" data-theme-toggle>Dark mode</button>'
)

SPECTATOR_PAGE_CSS = """
    :root{
      --bg:#f4f3ef;--bg-elevated:#faf9f6;--surface:#fff;--surface-muted:#fcfcfb;
      --text:#222;--text-secondary:#444;--muted:#666;--faint:#888;
      --border:#e4e2da;--border-strong:#d8d6ce;--row:#eceae4;
      --link:#3d6ea8;--code-bg:#f0eeea;
      --tag-live-bg:#d4edda;--tag-live-fg:#155724;--tag-done-bg:#f0f0f0;--tag-done-fg:#666;
      --turn-agent-bg:#e8f4ea;--turn-agent-fg:#1a6b2d;--turn-opp-bg:#f3f3f3;--turn-opp-fg:#555;
      --chip-agent-bg:#e8f0fe;--chip-agent-fg:#1a4fad;--chip-opp-bg:#f5f5f5;--chip-opp-fg:#444;
      --ok:#1a6b2d;--warn:#b45309;--shadow:rgba(0,0,0,.06);
      --input-bg:#fff;--input-border:#ccc;--btn-bg:#faf9f6;--btn-hover:#f0eeea;
      --err-bg:#fff8f0;--err-border:#f0d8b8;--ok-bg:#f0faf2;--ok-border:#c8e6ce;
      --eval-fill:#262421;--progress:#e8e6e0;
    }
    [data-theme="dark"]{
      --bg:#12141a;--bg-elevated:#1a1d26;--surface:#1e222c;--surface-muted:#232833;
      --text:#e8eaef;--text-secondary:#c8ccd6;--muted:#a0a6b4;--faint:#7a8190;
      --border:#2e3440;--border-strong:#3a4252;--row:#2a303c;
      --link:#7eb0e8;--code-bg:#2a303c;
      --tag-live-bg:#1e3a28;--tag-live-fg:#8fd9a8;--tag-done-bg:#2a303c;--tag-done-fg:#a0a6b4;
      --turn-agent-bg:#1e3a28;--turn-agent-fg:#8fd9a8;--turn-opp-bg:#2a303c;--turn-opp-fg:#c8ccd6;
      --chip-agent-bg:#1a2f4d;--chip-agent-fg:#9ec1f5;--chip-opp-bg:#2a303c;--chip-opp-fg:#c8ccd6;
      --ok:#8fd9a8;--warn:#e0a46a;--shadow:rgba(0,0,0,.35);
      --input-bg:#1a1d26;--input-border:#3a4252;--btn-bg:#232833;--btn-hover:#2a303c;
      --err-bg:#2a2218;--err-border:#5a4030;--ok-bg:#1a2a20;--ok-border:#2e4a38;
      --eval-fill:#0e0f12;--progress:#2a303c;
    }
    body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:24px 28px 40px;background:var(--bg);color:var(--text)}
    h1{margin:0 0 4px;font-size:1.35em}
    .sub{margin:0 0 18px;color:var(--muted);font-size:.88em;line-height:1.45;max-width:820px}
    h2{margin:24px 0 8px;font-size:1.05em;color:var(--text-secondary)}
    h3{margin:18px 0 6px;font-size:.82em;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:var(--faint)}
    .tabs{margin:12px 0 18px;display:flex;flex-wrap:wrap;align-items:center;gap:8px 0}
    .tabs a{margin-right:16px;text-decoration:none;color:var(--link);font-weight:600}
    .tabs a.active{color:var(--text);border-bottom:2px solid var(--text);padding-bottom:2px}
    .theme-toggle{margin-left:auto;font-size:.8em;padding:5px 10px;border-radius:6px;border:1px solid var(--border-strong);background:var(--btn-bg);color:var(--text-secondary);cursor:pointer;font-weight:600}
    .theme-toggle:hover{background:var(--btn-hover)}
    table{border-collapse:collapse;width:100%;max-width:920px;margin-top:6px;background:var(--surface);border:1px solid var(--border);border-radius:8px;overflow:hidden}
    th,td{border-bottom:1px solid var(--row);padding:10px 12px;text-align:left;font-size:.9em}
    th{background:var(--bg-elevated);font-weight:600;color:var(--muted)}
    tr:last-child td{border-bottom:none}
    tr:nth-child(even) td{background:var(--surface-muted)}
    .empty{color:var(--faint);margin-top:12px}
    code{font-size:.88em;background:var(--code-bg);padding:1px 5px;border-radius:4px}
    .ok{color:var(--ok);font-weight:600;font-size:.82em}
    .miss{color:var(--warn);font-weight:600;font-size:.82em}
    .g{border:1px solid var(--border);padding:14px 18px;margin:8px 0;border-radius:8px;background:var(--surface)}
    .g h3{margin:0 0 4px;font-size:1.05em}.g p{margin:3px 0;color:var(--muted);font-size:.88em}
    .g a{color:var(--link);text-decoration:none;font-weight:600}.g a:hover{text-decoration:underline}
    .tag{display:inline-block;font-size:.75em;padding:2px 8px;border-radius:3px;margin-left:6px}
    .live{background:var(--tag-live-bg);color:var(--tag-live-fg)}.done{background:var(--tag-done-bg);color:var(--tag-done-fg)}
    .btn-more{margin:16px 0 8px;font-size:.88em;padding:8px 14px;border-radius:6px;border:1px solid var(--border-strong);background:var(--btn-bg);color:var(--text);cursor:pointer;font-weight:600}
    .btn-more:hover{background:var(--btn-hover)}
    .done-meta{margin:0 0 8px}
    .active-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;margin-top:12px}
    .active-card{border:1px solid var(--border);border-radius:8px;background:var(--surface);padding:12px;display:flex;flex-direction:column;gap:10px}
    .active-card:hover{border-color:var(--border-strong);box-shadow:0 2px 8px var(--shadow)}
    .card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
    .card-head h3{margin:0;font-size:.95em;word-break:break-all}
    .turn-badge{font-size:.72em;padding:3px 8px;border-radius:999px;white-space:nowrap;font-weight:600}
    .turn-agent{background:var(--turn-agent-bg);color:var(--turn-agent-fg)}
    .turn-opponent{background:var(--turn-opp-bg);color:var(--turn-opp-fg)}
    .card-body{display:flex;gap:12px;align-items:flex-start}
    .board-eval-stage{display:flex;gap:6px;align-items:stretch;flex-shrink:0}
    .eval-col{display:flex;flex-direction:column;align-items:center;gap:4px;flex-shrink:0}
    .eval-track-v{width:14px;border-radius:2px;overflow:hidden;border:1px solid var(--faint);background:var(--surface);position:relative;flex-shrink:0}
    .eval-black{position:absolute;top:0;left:0;right:0;background:var(--eval-fill);transition:height .5s ease}
    .eval-score-v{font-size:.72em;font-weight:700;color:var(--text-secondary);margin-top:4px;text-align:center}
    .mini-board-wrap{flex-shrink:0}
    .mini-board{display:block;width:148px;height:148px;object-fit:cover;border:1px solid var(--border);border-radius:4px;background:var(--surface)}
    .card-meta{flex:1;min-width:0;font-size:.82em;color:var(--muted)}
    .chip-row{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
    .chip{padding:2px 7px;border-radius:4px;font-size:.78em;font-weight:600}
    .chip-agent{background:var(--chip-agent-bg);color:var(--chip-agent-fg)}
    .chip-opponent{background:var(--chip-opp-bg);color:var(--chip-opp-fg)}
    .meta-line{font-size:.75em;color:var(--faint);margin-top:4px}
    .card-foot{display:flex;justify-content:flex-end}
"""


def spectator_tabs(active: str) -> str:
    return (
        '<div class="tabs">'
        f'<a href="/spectator/"{" class=active" if active in ("active", "done", "spectator") else ""}>Spectator</a>'
        f'<a href="/create"{" class=active" if active == "create" else ""}>Create Game</a>'
        f'<a href="/calibration"{" class=active" if active == "calibration" else ""}>Calibration</a>'
        f'<a href="/leaderboard"{" class=active" if active == "ladder" else ""}>ELO Ladder</a>'
        '<button type="button" class="theme-toggle" data-theme-toggle>Dark mode</button>'
        "</div>"
    )
