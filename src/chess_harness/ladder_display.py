"""Shared agent + opponent ladder formatting for CLI and spectator."""

from __future__ import annotations

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


def format_agent_leaderboard_cli(ladder: ELOLadder) -> str:
    board = ladder.get_leaderboard()
    if not board:
        return "No inscribed models. Run: python play.py models list"
    lines = ["Agent rankings:"]
    for i, entry in enumerate(board, 1):
        label = entry["name"] if entry.get("name") != entry["model"] else entry["model"]
        games = entry.get("games", 0)
        g = f"{games} game" + ("" if games == 1 else "s")
        disabled = "" if entry.get("enabled", True) else " [disabled]"
        lines.append(f"  {i}. {label} ({entry['model']}): {entry['elo']} ELO — {g}{disabled}")
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
    <style>
    {SPECTATOR_PAGE_CSS}
    .catalog{{color:#999;font-size:.85em}}
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
    </body></html>"""


def render_calibration_html() -> str:
    return f"""<!DOCTYPE html><html><head><title>Calibration · Chess Vision Harness</title>
    <style>
    {SPECTATOR_PAGE_CSS}
    .progress{{height:10px;background:#e8e6e0;border-radius:6px;overflow:hidden;margin:8px 0 16px;max-width:480px}}
    .progress-fill{{height:100%;background:#3d6ea8;transition:width .4s ease}}
    .game-feed{{max-width:900px}}
    .game-line{{font-size:.85em;padding:8px 10px;border-bottom:1px solid #eceae4;background:#fff}}
    .game-line:last-child{{border-bottom:none}}
    .delta-up{{color:#1a6b2d}}.delta-down{{color:#b45309}}
    .playing-badge{{color:#155724;font-weight:600;font-size:.85em}}
    .idle-badge{{color:#999;font-size:.85em}}
    .cal-btn{{font-size:.8em;padding:4px 10px;border-radius:4px;border:1px solid #ccc;background:#fff;cursor:pointer;font-weight:600}}
    .cal-btn.start{{border-color:#3d6ea8;color:#3d6ea8}}
    .cal-btn.stop{{border-color:#b45309;color:#b45309}}
    .cal-btn:disabled{{opacity:.45;cursor:not-allowed}}
    .cal-controls{{display:flex;align-items:center;gap:6px;justify-content:flex-end}}
    .cal-par{{width:3em;padding:4px 6px;font-size:.85em;border:1px solid #ccc;border-radius:4px;text-align:center}}
    .cal-par:disabled{{background:#f5f5f5;color:#888}}
    .status-meta{{margin:0 0 12px;color:#888;font-size:.85em;min-height:1em}}
    .cal-toolbar{{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;margin:0 0 16px;padding:12px 14px;background:#fff;border:1px solid #e4e2da;border-radius:8px;max-width:920px}}
    .cal-toolbar label{{font-size:.85em;font-weight:600;color:#555}}
    .cal-toolbar select{{font-size:.85em;padding:5px 8px;border:1px solid #ccc;border-radius:4px;background:#fff}}
    .cal-btn.primary{{border-color:#3d6ea8;background:#3d6ea8;color:#fff}}
    .cal-legend{{font-size:.8em;color:#888;margin:0 0 8px}}
    </style></head><body>
    <h1>Engine Calibration</h1>
    {spectator_tabs("calibration")}
    <div class="cal-toolbar">
      <label for="pairing-mode">Opponent pairing</label>
      <select id="pairing-mode" onchange="onPairingModeChange(this.value)">
        <option value="floaters">Among floaters (ELO-weighted)</option>
        <option value="random">Random (any opponent)</option>
        <option value="anchors">Only vs Stockfish anchors</option>
        <option value="fixed">Fixed opponent</option>
      </select>
      <label for="fixed-opponent">Play against</label>
      <select id="fixed-opponent" disabled onchange="setFixedOpponent(this.value)"></select>
      <button class="cal-btn primary" id="start-all-btn" onclick="startAllEngines(this)">Start all (1 each)</button>
      <button class="cal-btn stop" id="stop-all-btn" onclick="stopAllEngines(this)">Stop all</button>
    </div>
    <div id="status-meta" class="status-meta"></div>
    <h2>Calibrated ratings</h2>
    <table id="rating-table"><tr><th>ID</th><th>Calibrated ELO</th><th>Games</th><th>Activity</th><th></th></tr>
    <tr><td colspan="5" class="empty">No calibration data yet.</td></tr></table>
    <h2>Recent games</h2>
    <p class="cal-legend">Green = ELO gain · Orange = ELO loss (per engine updated after that game)</p>
    <div id="game-feed" class="game-feed"></div>
    <script>
    function esc(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}}
    function readParallel(id){{
      const inp=document.querySelector('input.cal-par[data-eid="'+id+'"]');
      const n=parseInt(inp&&inp.value?inp.value:'1',10);
      return Math.max(1,Math.min(100,isNaN(n)?1:n));
    }}
    function savedParallel(id,fallback){{
      const inp=document.querySelector('input.cal-par[data-eid="'+id+'"]');
      if(inp&&!inp.disabled&&inp.value)return inp.value;
      return String(fallback);
    }}
    async function setPairingMode(mode){{
      try{{
        await fetch('/api/calibration/pairing-mode?mode='+encodeURIComponent(mode),{{method:'POST'}});
      }}catch(e){{}}
    }}
    function onPairingModeChange(mode){{
      const fix=document.getElementById('fixed-opponent');
      if(fix)fix.disabled=(mode!=='fixed');
      setPairingMode(mode);
    }}
    async function setFixedOpponent(opponent){{
      if(!opponent)return;
      try{{
        await fetch('/api/calibration/fixed-opponent?opponent='+encodeURIComponent(opponent),{{method:'POST'}});
      }}catch(e){{}}
    }}
    async function startAllEngines(btn){{
      if(btn)btn.disabled=true;
      try{{
        await fetch('/api/calibration/start-all?parallel=1',{{method:'POST'}});
      }}finally{{
        if(btn)btn.disabled=false;
        refresh();
      }}
    }}
    async function stopAllEngines(btn){{
      if(btn)btn.disabled=true;
      try{{
        await fetch('/api/calibration/stop-all',{{method:'POST'}});
      }}finally{{
        if(btn)btn.disabled=false;
        refresh();
      }}
    }}
    async function setContinuous(id,start,btn){{
      if(btn)btn.disabled=true;
      let path='/api/calibration/continuous/'+encodeURIComponent(id)+(start?'/start':'/stop');
      if(start)path+='?parallel='+readParallel(id);
      try{{
        await fetch(path,{{method:'POST'}});
      }}finally{{
        if(btn)btn.disabled=false;
        refresh();
      }}
    }}
    async function refresh(){{
      try{{
        const r=await fetch('/api/calibration/status');
        const d=await r.json();
        let meta='';
        if(d.pairing_mode)meta+='Pairing: '+d.pairing_mode;
        if(d.pairing_mode==='fixed'&&d.fixed_opponent_id)meta+=(meta?' · ':'')+'vs '+d.fixed_opponent_id;
        if(d.skipped_games)meta+=(meta?' · ':'')+d.skipped_games+' games skipped (timeout)';
        document.getElementById('status-meta').textContent=meta;
        const modeSel=document.getElementById('pairing-mode');
        if(modeSel&&d.pairing_mode){{
          modeSel.value=d.pairing_mode;
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
        const rows=(d.rating_table||[]).map(row=>{{
          const elo=row.uncalibrated?`<span class="catalog">${{row.elo}}*</span>`:`<strong>${{row.elo}}</strong>`;
          let activity='<span class="idle-badge">—</span>';
          if(row.playing>0){{
            activity=`<span class="playing-badge">${{row.playing}} game${{row.playing===1?'':'s'}} live</span>`;
          }}else if(row.continuous){{
            activity='<span class="playing-badge">running</span>';
          }}else if(row.activity==='disabled'||row.enabled===false){{
            activity='<span class="idle-badge">disabled</span>';
          }}
          let ctrl='';
          if(row.can_calibrate){{
            const parVal=row.continuous?String(row.parallel||1):savedParallel(row.id,1);
            const parDisabled=row.continuous?' disabled':'';
            const parInput=`<input class="cal-par" type="number" min="1" max="100" value="${{parVal}}" data-eid="${{esc(row.id)}}"${{parDisabled}} title="Parallel games">`;
            if(row.continuous){{
              ctrl=`<div class="cal-controls">${{parInput}}<button class="cal-btn stop" data-eid="${{esc(row.id)}}" onclick="setContinuous(this.getAttribute('data-eid'),false,this)">Stop</button></div>`;
            }}else{{
              ctrl=`<div class="cal-controls">${{parInput}}<button class="cal-btn start" data-eid="${{esc(row.id)}}" onclick="setContinuous(this.getAttribute('data-eid'),true,this)">Start</button></div>`;
            }}
          }}
          return `<tr><td><code>${{esc(row.id)}}</code></td><td>${{elo}}</td><td>${{row.games||0}}</td><td>${{activity}}</td><td>${{ctrl}}</td></tr>`;
        }}).join('');
        rt.innerHTML='<tr><th>ID</th><th>Calibrated ELO</th><th>Games</th><th>Activity</th><th></th></tr>'
          +(rows||'<tr><td colspan="5" class="empty">No ratings yet.</td></tr>');
        const feed=document.getElementById('game-feed');
        const games=(d.recent_games||[]).slice().reverse();
        feed.innerHTML=games.length?games.map(g=>{{
          let upd='';
          (g.updates||[]).forEach(u=>{{
            const cls=u.elo_delta>=0?'delta-up':'delta-down';
            const sign=u.elo_delta>=0?'+':'';
            upd+=` <span class="${{cls}}">${{esc(u.opponent_id)}} ${{u.elo_before}}→${{u.elo_after}} (${{sign}}${{u.elo_delta.toFixed(1)}})</span>`;
          }});
          const skip=g.skipped?' <span class="idle-badge">(no ELO change)</span>':'';
          return `<div class="game-line">#${{g.game_index||'?'}} <strong>${{esc(g.white)}}</strong> vs <strong>${{esc(g.black)}}</strong> → ${{esc(g.result)}}${{skip}}${{upd}}</div>`;
        }}).join(''):'<p class="empty">No games logged yet.</p>';
      }}catch(e){{}}
    }}
    refresh();setInterval(refresh,2000);
    </script></body></html>"""


SPECTATOR_PAGE_CSS = """
    body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:24px 28px 40px;background:#f4f3ef;color:#222}
    h1{margin:0 0 4px;font-size:1.35em}
    .sub{margin:0 0 18px;color:#666;font-size:.88em;line-height:1.45;max-width:820px}
    h2{margin:24px 0 8px;font-size:1.05em;color:#444}
    h3{margin:18px 0 6px;font-size:.82em;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:#888}
    .tabs{margin:12px 0 18px}.tabs a{margin-right:16px;text-decoration:none;color:#3d6ea8;font-weight:600}
    .tabs a.active{color:#222;border-bottom:2px solid #222;padding-bottom:2px}
    table{border-collapse:collapse;width:100%;max-width:920px;margin-top:6px;background:#fff;border:1px solid #e4e2da;border-radius:8px;overflow:hidden}
    th,td{border-bottom:1px solid #eceae4;padding:10px 12px;text-align:left;font-size:.9em}
    th{background:#faf9f6;font-weight:600;color:#555}
    tr:last-child td{border-bottom:none}
    tr:nth-child(even) td{background:#fcfcfb}
    .empty{color:#888;margin-top:12px}
    code{font-size:.88em;background:#f0eeea;padding:1px 5px;border-radius:4px}
    .ok{color:#1a6b2d;font-weight:600;font-size:.82em}
    .miss{color:#b45309;font-weight:600;font-size:.82em}
    .g{border:1px solid #e4e2da;padding:14px 18px;margin:8px 0;border-radius:8px;background:#fff}
    .g h3{margin:0 0 4px;font-size:1.05em}.g p{margin:3px 0;color:#666;font-size:.88em}
    .g a{color:#3d6ea8;text-decoration:none;font-weight:600}.g a:hover{text-decoration:underline}
    .tag{display:inline-block;font-size:.75em;padding:2px 8px;border-radius:3px;margin-left:6px}
    .live{background:#d4edda;color:#155724}.done{background:#f0f0f0;color:#666}
    .active-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:14px;margin-top:12px}
    .active-card{border:1px solid #e4e2da;border-radius:8px;background:#fff;padding:12px;display:flex;flex-direction:column;gap:10px}
    .active-card:hover{border-color:#bbb;box-shadow:0 2px 8px rgba(0,0,0,.06)}
    .card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
    .card-head h3{margin:0;font-size:.95em;word-break:break-all}
    .turn-badge{font-size:.72em;padding:3px 8px;border-radius:999px;white-space:nowrap;font-weight:600}
    .turn-agent{background:#e8f4ea;color:#1a6b2d}
    .turn-opponent{background:#f3f3f3;color:#555}
    .card-body{display:flex;gap:12px;align-items:flex-start}
    .board-eval-stage{display:flex;gap:6px;align-items:stretch;flex-shrink:0}
    .eval-col{display:flex;flex-direction:column;align-items:center;gap:4px;flex-shrink:0}
    .eval-track-v{width:14px;border-radius:2px;overflow:hidden;border:1px solid #888;background:#fff;position:relative;flex-shrink:0}
    .eval-black{position:absolute;top:0;left:0;right:0;background:#262421;transition:height .5s ease}
    .eval-score-v{font-size:.72em;font-weight:700;color:#444;margin-top:4px;text-align:center}
    .mini-board-wrap{flex-shrink:0}
    .mini-board{display:block;width:148px;height:148px;object-fit:cover;border:1px solid #ddd;border-radius:4px;background:#fff}
    .card-meta{flex:1;min-width:0;font-size:.82em;color:#555}
    .chip-row{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
    .chip{padding:2px 7px;border-radius:4px;font-size:.78em;font-weight:600}
    .chip-agent{background:#e8f0fe;color:#1a4fad}
    .chip-opponent{background:#f5f5f5;color:#444}
    .meta-line{font-size:.75em;color:#888;margin-top:4px}
    .card-foot{display:flex;justify-content:flex-end}
"""


def spectator_tabs(active: str) -> str:
    return (
        '<div class="tabs">'
        f'<a href="/?tab=active"{" class=active" if active == "active" else ""}>Active</a>'
        f'<a href="/?tab=done"{" class=active" if active == "done" else ""}>Completed</a>'
        f'<a href="/calibration"{" class=active" if active == "calibration" else ""}>Calibration</a>'
        f'<a href="/leaderboard"{" class=active" if active == "ladder" else ""}>ELO Ladder</a>'
        "</div>"
    )
