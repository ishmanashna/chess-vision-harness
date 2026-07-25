"""
Spectator web interface for Chess Vision Harness.
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, Optional

from contextlib import asynccontextmanager

import chess
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse

from .agent_surface import agent_safe_spectator_state, debug_state_enabled
from .api_v1 import mount_api_v1
from .board_controller import BoardController
from .elo import ELOLadder
from .ladder_display import (
    SPECTATOR_PAGE_CSS,
    THEME_INIT_SCRIPT,
    THEME_TOGGLE_SCRIPT,
    render_calibration_html,
    render_leaderboard_html,
    spectator_tabs,
)
from .create_game_page import handle_create_game_post, render_create_game_page
from .calibration_view import get_calibration_status, rebuild_merged_ratings_file
from .continuous_calibration import can_continuously_calibrate, get_continuous_calibration
from .engine import EvalEngineAdapter
from .game_manager import GameManager
from .game_service import GameService
from .paths import project_root, resolve_base_dir
from .serve_utils import remove_spectator_meta

_project_root = project_root()
_base = str(resolve_base_dir())
game_manager = GameManager(base_dir=_base)


def _ladder() -> ELOLadder:
    return ELOLadder(base_dir=_base)


_engine: Optional[EvalEngineAdapter] = None
_controller: Optional[BoardController] = None
_game_service: Optional[GameService] = None
_eval_cache: Dict[str, tuple[float, Optional[int]]] = {}
_finished_eval_cache: Dict[str, int] = {}
_EVAL_TTL = 2.0

NAV = (
    '<a class="back" href="/?tab=active">&larr; Active</a> &nbsp;|&nbsp; '
    '<a class="back" href="/?tab=done">Completed</a> &nbsp;|&nbsp; '
    '<a class="back" href="/calibration">Calibration</a> &nbsp;|&nbsp; '
    '<a class="back" href="/leaderboard">ELO Ladder</a> &nbsp;|&nbsp; '
    '<button type="button" class="theme-toggle theme-toggle-inline" data-theme-toggle>Dark mode</button>'
)


def _game_summary(state: Dict[str, Any]) -> str:
    return _get_controller().format_spectator_summary(state)


def _game_elo_change(state: Dict[str, Any], game_id: str) -> Optional[Dict[str, int]]:
    return _get_controller().apply_elo_delta({**state, "game_id": game_id})


def _format_elo_change(delta: Optional[Dict[str, int]], state: Dict[str, Any]) -> str:
    agent = state.get("model_display_name") or state.get("model_name") or "Agent"
    return BoardController.format_elo_change(delta, agent)


def _clear_stale_batch_calibration() -> None:
    """Remove leftover CLI batch live state so it is not mistaken for UI calibration."""
    live = _project_root / "elo_calibration" / "results" / "live_session.json"
    if live.exists():
        live.unlink()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    _clear_stale_batch_calibration()
    rebuild_merged_ratings_file()
    async def _idle_watcher():
        while True:
            await asyncio.sleep(60)
            try:
                await asyncio.to_thread(_get_game_service().prune_idle_games)
            except Exception:
                pass

    task = asyncio.create_task(_idle_watcher())
    yield
    task.cancel()
    await get_continuous_calibration().stop_all()
    _get_game_service().controller.opponent_mgr.release()
    remove_spectator_meta()
    global _engine
    if _engine is not None:
        _engine.quit()
        _engine = None


app = FastAPI(title="Chess Vision Harness Spectator", lifespan=_lifespan)


def _get_engine() -> Optional[EvalEngineAdapter]:
    global _engine
    if _engine is None:
        try:
            _engine = EvalEngineAdapter()
        except RuntimeError:
            return None
    return _engine


def _get_controller() -> BoardController:
    global _controller
    if _controller is None:
        _controller = BoardController(game_manager)
    return _controller


def _get_game_service() -> GameService:
    global _game_service
    if _game_service is None:
        # Share one BoardController with display helpers (no dual engine managers).
        _game_service = GameService(game_manager, controller=_get_controller())
    return _game_service


mount_api_v1(app, _get_game_service)


@app.get("/health")
async def health():
    return {"ok": True, "status": "up"}


def _eval_position(fen: str) -> Optional[int]:
    eng = _get_engine()
    if eng is None:
        return None
    now = time.time()
    cached = _eval_cache.get(fen)
    if cached and now - cached[0] < _EVAL_TTL:
        return cached[1]
    board = chess.Board(fen)
    score = eng.evaluate(board, depth=8)
    _eval_cache[fen] = (now, score)
    return score


def _board_stack_labels(labels: Dict[str, str], agent_color: str) -> Dict[str, str]:
    """Map chess-color labels to physical top/bottom on the rendered board (agent at bottom)."""
    if agent_color == "BLACK":
        return {"top": labels["white"], "bottom": labels["black"]}
    return {"top": labels["black"], "bottom": labels["white"]}


def _eval_ui(
    score_white: Optional[int],
    labels: Dict[str, str],
    agent_color: str = "WHITE",
) -> Dict[str, Any]:
    """Vertical eval aligned to board orientation (agent at bottom).

    Dark segment = Black's share. When the agent is Black (black at bottom of
    the board), that segment grows from the bottom so the bar matches the board.
    """
    stack = _board_stack_labels(labels, agent_color)
    black_at_bottom = agent_color == "BLACK"
    base = {
        "black_label": labels["black"],
        "white_label": labels["white"],
        "top_label": stack["top"],
        "bottom_label": stack["bottom"],
        "black_at_bottom": black_at_bottom,
    }
    if score_white is None:
        return {**base, "black_pct": "50%", "text": "—"}
    black_pct = max(4, min(96, 50 - score_white / 25))
    pawns = score_white / 100
    sign = "+" if pawns > 0 else ""
    return {**base, "black_pct": f"{black_pct:.1f}%", "text": f"{sign}{pawns:.1f}"}


def _resolve_eval_cp(state: Dict[str, Any], game_id: str) -> Optional[int]:
    if state.get("last_eval_cp") is not None:
        return state["last_eval_cp"]
    if state.get("status") == "in_progress":
        return _eval_position(state["board_fen"])
    if game_id in _finished_eval_cache:
        return _finished_eval_cache[game_id]
    score = _eval_position(state["board_fen"])
    if score is not None:
        _finished_eval_cache[game_id] = score
    return score


def _move_rows(state: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Build Lichess-style move rows (SAN) from stored UCI plies."""
    moves = state.get("moves", [])
    if not moves:
        return []
    board = chess.Board(state.get("start_fen", chess.STARTING_FEN))
    rows: list[Dict[str, Any]] = []
    i = 0
    move_num = 1
    while i < len(moves):
        white = board.san(chess.Move.from_uci(moves[i]))
        board.push(chess.Move.from_uci(moves[i]))
        i += 1
        black = ""
        if i < len(moves):
            black = board.san(chess.Move.from_uci(moves[i]))
            board.push(chess.Move.from_uci(moves[i]))
            i += 1
        rows.append({"num": move_num, "white": white, "black": black})
        move_num += 1
    return rows


def _active_card(state: Dict[str, Any], game_id: str) -> Dict[str, Any]:
    ctrl = _get_controller()
    board = chess.Board(state["board_fen"])
    persp = ctrl._perspective(board, state["agent_color"])
    elo = ctrl._elo_context(state)
    score_white = _eval_position(state["board_fen"])
    labels = BoardController.side_labels(state)
    eval_ui = _eval_ui(score_white, labels, state["agent_color"])
    model = state.get("model_display_name") or state.get("model_name") or "Agent"
    opponent_label = BoardController.engine_display_label(state)
    turn = "Agent to move" if persp["your_turn"] else "Opponent to move"
    if persp["in_check"] and persp["your_turn"]:
        turn += " · check"
    return {
        "agent_name": model,
        "agent_color": state["agent_color"],
        "opponent_label": opponent_label,
        "engine_label": opponent_label,
        "opponent_id": state.get("opponent_id"),
        "agent_elo": elo.get("agent_elo"),
        "opponent_elo": elo.get("opponent_elo"),
        "engine_elo": elo.get("engine_elo"),
        "move_number": board.fullmove_number,
        "plies": len(state.get("moves", [])),
        "your_turn": persp["your_turn"],
        "turn_label": turn,
        "eval_white_cp": score_white,
        "eval_ui": eval_ui,
        "board_url": f"/g/{game_id}/board.png",
        "board_cache": f"{len(state.get('moves', []))}:{state.get('last_move_uci') or ''}",
    }


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    tab = request.query_params.get("tab", "active")
    if tab not in ("active", "done"):
        tab = "active"
    html = (
        f"""<!DOCTYPE html><html><head><title>Chess Vision Harness</title>
    {THEME_INIT_SCRIPT}
    <style>
    {SPECTATOR_PAGE_CSS}
    </style></head><body>
    <h1>Chess Vision Harness</h1>
    {spectator_tabs(tab)}
    <div id="g"></div>
    <script>
    const tab={tab!r};
    const activeCards=new Map();
    """
        + """
    function evalFromUi(ev){
      if(!ev)return{blackPct:'50%',text:'—',black:'Black',white:'White',blackAtBottom:false};
      return{blackPct:ev.black_pct||'50%',text:ev.text,black:ev.black_label,white:ev.white_label,blackAtBottom:!!ev.black_at_bottom};
    }

    function applyEvalBar(el, ev){
      if(!el||!ev)return;
      el.style.height=ev.blackPct||'50%';
      if(ev.blackAtBottom){el.style.top='auto';el.style.bottom='0';}
      else{el.style.top='0';el.style.bottom='auto';}
    }

    function syncMiniEvalHeights(){
      document.querySelectorAll('.board-eval-stage').forEach(stage=>{
        const img=stage.querySelector('.mini-board');
        const track=stage.querySelector('.eval-track-v');
        if(img&&track&&img.offsetHeight)track.style.height=img.offsetHeight+'px';
      });
    }

    function renderActiveCard(g){
      const c=g.active_card||{};
      const ev=evalFromUi(c.eval_ui);
      const oppLabel=c.opponent_label||c.engine_label||'Opponent';
      const oppElo=c.opponent_elo!=null?c.opponent_elo:c.engine_elo;
      const turnCls=c.your_turn?'turn-agent':'turn-opponent';
      const agentElo=c.agent_elo!=null?' ('+c.agent_elo+')':'';
      const engElo=oppElo!=null?' ('+oppElo+')':'';
      const el=document.createElement('div');
      el.className='active-card';
      el.dataset.gameId=g.game_id;
      el.innerHTML=`
        <div class="card-head">
          <h3>${g.game_id} <span class="tag live">live</span></h3>
          <span class="turn-badge ${turnCls}">${c.turn_label||g.turn}</span>
        </div>
        <div class="card-body">
          <div class="board-eval-stage">
            <div class="eval-col">
              <div class="eval-track-v"><div class="eval-black" style="height:${ev.blackPct};${ev.blackAtBottom?'top:auto;bottom:0':'top:0;bottom:auto'}"></div></div>
              <div class="eval-score-v">${ev.text}</div>
            </div>
            <a class="mini-board-wrap" href="/g/${g.game_id}"><img class="mini-board" src="${c.board_url}?v=${c.board_cache||0}" alt="board" onload="syncMiniEvalHeights()"/></a>
          </div>
          <div class="card-meta">
            <div class="chip-row">
              <span class="chip chip-agent">${c.agent_name||'Agent'}${agentElo} · ${c.agent_color||'?'}</span>
              <span class="chip chip-opponent">${oppLabel}${engElo}</span>
            </div>
            <div class="meta-line">${ev.white} vs ${ev.black} · Move ${c.move_number||'?'} · ${c.plies||0} half-moves</div>
          </div>
        </div>
        <div class="card-foot"><a href="/g/${g.game_id}">Watch full board →</a></div>`;
      return el;
    }

    function updateActiveCard(el,g){
      const c=g.active_card||{};
      const ev=evalFromUi(c.eval_ui);
      const turnCls=c.your_turn?'turn-agent':'turn-opponent';
      el.querySelector('.turn-badge').className='turn-badge '+turnCls;
      el.querySelector('.turn-badge').textContent=c.turn_label||g.turn;
      const img=el.querySelector('.mini-board');
      const nextSrc=`${c.board_url}?v=${c.board_cache||0}`;
      if(img.getAttribute('src')!==nextSrc)img.setAttribute('src',nextSrc);
      applyEvalBar(el.querySelector('.eval-black'), ev);
      el.querySelector('.eval-score-v').textContent=ev.text;
      el.querySelector('.meta-line').textContent=`${ev.white} vs ${ev.black} · Move ${c.move_number||'?'} · ${c.plies||0} half-moves`;
      syncMiniEvalHeights();
    }

    async function f(){
      const c=document.getElementById('g');
      if(tab==='active'){
        const r=await fetch('/api/games?status=in_progress');
        const payload=await r.json();
        const active=payload.games||payload;
        if(!active.length){
          c.innerHTML='<p>No active games. <a href="/?tab=done">View completed</a></p>';
          activeCards.clear();
          return;
        }
        let grid=c.querySelector('.active-grid');
        if(!grid){
          c.innerHTML='';
          grid=document.createElement('div');
          grid.className='active-grid';
          c.appendChild(grid);
        }
        const seen=new Set();
        for(const g of active){
          seen.add(g.game_id);
          const prev=activeCards.get(g.game_id);
          if(!prev){
            const card=renderActiveCard(g);
            grid.appendChild(card);
            activeCards.set(g.game_id,{el:card,revision:g.revision});
          }else if(prev.revision!==g.revision){
            updateActiveCard(prev.el,g);
            activeCards.set(g.game_id,{el:prev.el,revision:g.revision});
          }
        }
        for(const [id,info] of [...activeCards.entries()]){
          if(!seen.has(id)){info.el.remove();activeCards.delete(id);}
        }
      }else{
        await renderDonePage(false);
      }
    }

    const DONE_PAGE=40;
    let doneOffset=0;
    let doneTotal=0;
    let doneLoading=false;

    function appendDoneGames(games){
      const c=document.getElementById('g');
      let list=c.querySelector('.done-list');
      if(!list){
        c.innerHTML='';
        const head=document.createElement('p');
        head.className='done-meta sub';
        head.id='done-meta';
        c.appendChild(head);
        list=document.createElement('div');
        list.className='done-list';
        c.appendChild(list);
        const more=document.createElement('button');
        more.type='button';
        more.className='btn-more';
        more.id='done-more';
        more.textContent='Load more';
        more.onclick=()=>renderDonePage(true);
        c.appendChild(more);
      }
      for(const g of games){
        const tag=g.result||'done';
        const outcome=(g.agent_outcome&&g.agent_outcome.label)?` · ${g.agent_outcome.label}`:'';
        list.insertAdjacentHTML('beforeend',`<div class="g"><h3>${g.game_id} <span class="tag done">${tag}</span></h3>
          <p>${g.summary||''}${outcome}</p>
          ${g.elo_change?`<p>${g.elo_change}</p>`:''}
          <a href="/g/${g.game_id}">Review</a></div>`);
      }
      const meta=document.getElementById('done-meta');
      if(meta)meta.textContent=`Showing ${Math.min(doneOffset,doneTotal)} of ${doneTotal} completed (newest first)`;
      const btn=document.getElementById('done-more');
      if(btn)btn.style.display=doneOffset<doneTotal?'inline-block':'none';
    }

    async function renderDonePage(append){
      if(doneLoading)return;
      doneLoading=true;
      try{
        if(!append){doneOffset=0;document.getElementById('g').innerHTML='';}
        const r=await fetch(`/api/games?status=finished&limit=${DONE_PAGE}&offset=${doneOffset}`);
        const payload=await r.json();
        const games=payload.games||[];
        doneTotal=payload.total||games.length;
        if(!append && !games.length){
          document.getElementById('g').innerHTML='<p>No completed games yet.</p>';
          return;
        }
        doneOffset+=games.length;
        appendDoneGames(games);
      }finally{doneLoading=false;}
    }

    f();
    if(tab==='active')setInterval(f,3000);
    </script>
    """
        + THEME_TOGGLE_SCRIPT
        + """</body></html>"""
    )
    return HTMLResponse(html)


@app.get("/create", response_class=HTMLResponse)
async def create_game_get():
    return HTMLResponse(render_create_game_page())


@app.post("/create", response_class=HTMLResponse)
async def create_game_post(request: Request):
    form = await request.form()
    fields = {k: str(v) for k, v in form.items()}
    html_out, _game_id, _brief, _echo = handle_create_game_post(fields, _get_game_service())
    return HTMLResponse(html_out)


@app.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard():
    return HTMLResponse(render_leaderboard_html(_ladder()))


@app.get("/calibration", response_class=HTMLResponse)
async def calibration_page():
    return HTMLResponse(render_calibration_html())


@app.get("/api/calibration/status")
async def calibration_status():
    return get_calibration_status()


@app.post("/api/calibration/continuous/{engine_id}/start")
async def calibration_continuous_start(engine_id: str, parallel: int = Query(1, ge=1, le=100)):
    if not can_continuously_calibrate(engine_id):
        raise HTTPException(400, f"Engine cannot be continuously calibrated: {engine_id}")
    try:
        await get_continuous_calibration().start(engine_id, parallel=parallel)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "engine_id": engine_id, "running": True, "parallel": parallel}


@app.post("/api/calibration/continuous/{engine_id}/stop")
async def calibration_continuous_stop(engine_id: str):
    await get_continuous_calibration().stop(engine_id)
    return {"ok": True, "engine_id": engine_id, "running": False}


@app.post("/api/calibration/pairing-mode")
async def calibration_set_pairing_mode(mode: str = Query(...)):
    try:
        pairing_mode = get_continuous_calibration().set_pairing_mode(mode)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "pairing_mode": pairing_mode}


@app.post("/api/calibration/start-all")
async def calibration_start_all(parallel: int = Query(1, ge=1, le=100)):
    started = await get_continuous_calibration().start_all(parallel=parallel)
    return {"ok": True, "started": started, "count": len(started), "parallel": parallel}


@app.post("/api/calibration/stop-all")
async def calibration_stop_all():
    stopped = await get_continuous_calibration().stop_all()
    return {"ok": True, "stopped": stopped, "count": len(stopped)}


@app.post("/api/calibration/fixed-opponent")
async def calibration_set_fixed_opponent(opponent: str = Query(...)):
    try:
        opponent_id = get_continuous_calibration().set_fixed_opponent(opponent)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "fixed_opponent_id": opponent_id}


@app.get("/g/{game_id}", response_class=HTMLResponse)
async def game_view(game_id: str):
    html = f"""<!DOCTYPE html><html><head><title>{game_id} · Chess Vision Harness</title>
    {THEME_INIT_SCRIPT}
    <style>
    {SPECTATOR_PAGE_CSS}
    *{{box-sizing:border-box}}
    body{{padding:0;min-height:100vh}}
    a{{color:var(--link);text-decoration:none}}a:hover{{text-decoration:underline}}
    .page-header{{padding:16px 32px;display:flex;flex-wrap:wrap;align-items:center;gap:8px 24px;border-bottom:1px solid var(--border);background:var(--bg-elevated)}}
    .page-header .nav{{font-size:.9em;color:var(--muted);display:flex;flex-wrap:wrap;align-items:center;gap:4px 0;width:100%}}
    .theme-toggle-inline{{margin-left:8px;vertical-align:middle}}
    .page-header h1{{margin:0;font-size:1.2em;font-weight:600}}
    .page-header .gid{{color:var(--faint);font-weight:400;font-size:.85em}}
    .layout{{display:grid;grid-template-columns:minmax(280px,360px) auto minmax(200px,280px);gap:28px;align-items:start;padding:24px 32px 40px;max-width:1320px;margin:0 auto}}
    .col h2{{margin:0 0 12px;font-size:.7em;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--faint)}}
    .info-col{{display:flex;flex-direction:column;gap:16px}}
    .info-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:18px 20px}}
    .info-card h2{{margin:0 0 10px;font-size:.7em;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--faint)}}
    .meta-grid{{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;font-size:.86em;line-height:1.45}}
    .meta-grid dt{{color:var(--faint);margin:0}}
    .meta-grid dd{{margin:0;color:var(--text-secondary);word-break:break-word}}
    #state-result{{font-weight:700}}
    .actions{{display:flex;flex-direction:column;gap:8px}}
    .btn{{display:block;width:100%;padding:9px 12px;font-size:.86em;border:1px solid var(--border-strong);border-radius:6px;background:var(--btn-bg);color:var(--text);cursor:pointer;text-align:center;text-decoration:none}}
    .btn:hover{{background:var(--btn-hover);border-color:var(--border-strong)}}
    .btn-hint{{font-size:.78em;color:var(--faint);min-height:1.2em}}
    .board-col{{display:flex;justify-content:center}}
    .board-stack{{display:inline-flex;flex-direction:column;border:1px solid var(--border-strong);border-radius:10px;overflow:hidden;background:var(--surface);box-shadow:0 1px 4px var(--shadow)}}
    .board-label{{padding:11px 16px;text-align:center;font-size:.93em;font-weight:600;background:var(--bg-elevated);color:var(--text)}}
    .board-label.black{{border-bottom:1px solid var(--border)}}
    .board-label.white{{border-top:1px solid var(--border)}}
    .board-label .sub{{display:block;font-size:.76em;font-weight:400;color:var(--faint);margin-top:3px}}
    .board-row{{display:flex;align-items:stretch}}
    .eval-col-v{{display:flex;flex-direction:column;align-items:center;flex-shrink:0;border-right:1px solid var(--border);background:var(--bg-elevated);padding:0}}
    .eval-track-v{{width:18px;background:var(--surface);position:relative;flex-shrink:0;border:1px solid var(--border-strong);border-radius:2px;flex:1;min-height:120px;margin:0}}
    .eval-black{{position:absolute;top:0;left:0;right:0;background:var(--eval-fill);transition:height .5s ease}}
    #board{{display:block;background:var(--surface);width:min(calc(100vh - 180px),calc(100vw - 560px),600px);height:auto}}
    .moves-col{{display:flex;flex-direction:column;min-height:0;max-height:calc(100vh - 100px)}}
    .moves-col .panel{{background:var(--surface);border:1px solid var(--border);border-radius:8px;display:flex;flex-direction:column;flex:1;min-height:200px;overflow:hidden}}
    .moves-col .panel h2{{padding:14px 16px 0;margin:0}}
    .moves-scroll{{overflow-y:auto;flex:1;padding:8px 12px 14px}}
    .move-row{{display:grid;grid-template-columns:26px 1fr 1fr;gap:8px;padding:7px 4px;font-size:.88em;border-bottom:1px solid var(--row)}}
    .move-row:last-child{{border-bottom:none}}
    .move-row .mn{{color:var(--faint);text-align:right;font-size:.82em}}
    .move-row .w.on,.move-row .b.on{{font-weight:700}}
    @media(max-width:960px){{
      .layout{{grid-template-columns:1fr;gap:24px}}
      .moves-col{{max-height:320px}}
      #board{{width:100%;max-width:480px}}
    }}
    </style></head><body>
    <header class="page-header">
      <div class="nav">{NAV}</div>
    </header>
    <div class="layout">
      <aside class="col info-col">
        <div class="info-card">
          <h2>Game info</h2>
          <dl class="meta-grid" id="meta"></dl>
        </div>
        <div class="info-card">
          <h2>Game state</h2>
          <dl class="meta-grid" id="state-meta">
            <dt>Result</dt><dd id="state-result">—</dd>
            <dt>Termination</dt><dd id="state-termination">—</dd>
            <dt>Evaluation</dt><dd id="state-eval">—</dd>
            <dt>ELO change</dt><dd id="state-elo">—</dd>
          </dl>
        </div>
        <div class="info-card">
          <h2>Export</h2>
          <div class="actions">
            <a class="btn" href="/g/{game_id}/board.png" download="{game_id}-board.png">Download board PNG</a>
            <button type="button" class="btn" id="copy-pgn">Copy PGN</button>
            <span class="btn-hint" id="action-hint"></span>
          </div>
        </div>
      </aside>
      <div class="col board-col" id="board-col">
        <div class="board-stack">
          <div class="board-label black" id="lbl-black">Black</div>
          <div class="board-row">
            <div class="eval-col-v">
              <div class="eval-track-v" id="eval-track"><div class="eval-black" id="eval-black" style="height:50%"></div></div>
            </div>
            <img id="board" src="/g/{game_id}/board.png" alt="chess board"/>
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
    <script>
    let lastRevision='';
    let lastMoveCount=0;
    let lastPgn='';

    function syncHeights(){{
      const board=document.getElementById('board');
      const track=document.getElementById('eval-track');
      const boardCol=document.getElementById('board-col');
      const movesCol=document.getElementById('moves-col');
      const stack=document.querySelector('.board-stack');
      if(board&&track&&board.offsetHeight)track.style.height=board.offsetHeight+'px';
      if(stack&&movesCol)movesCol.style.maxHeight=stack.offsetHeight+'px';
    }}

    function playerLine(name,elo){{
      if(elo==null)return name;
      return name+' ('+elo+')';
    }}

    function renderGameState(s,ev){{
      const result=document.getElementById('state-result');
      const term=document.getElementById('state-termination');
      const evalEl=document.getElementById('state-eval');
      const eloEl=document.getElementById('state-elo');
      if(result)result.textContent=s.game_over?(s.result||'—'):'In progress';
      if(term)term.textContent=s.end_reason_label||'—';
      if(evalEl){{
        const t=ev&&ev.text&&ev.text!=='—'?ev.text:'—';
        evalEl.textContent=t;
      }}
      if(eloEl)eloEl.textContent=s.elo_change||'No ELO change recorded yet.';
    }}

    function setLabels(ev,s){{
      if(!ev)return;
      document.getElementById('lbl-black').textContent=ev.top_label||ev.black_label||'Black';
      document.getElementById('lbl-white').textContent=ev.bottom_label||ev.white_label||'White';
      const bar=document.getElementById('eval-black');
      bar.style.height=ev.black_pct||'50%';
      if(ev.black_at_bottom){{bar.style.top='auto';bar.style.bottom='0';}}
      else{{bar.style.top='0';bar.style.bottom='auto';}}
      renderGameState(s,ev);
    }}

    function nameWithoutElo(name){{
      if(!name)return'';
      return name.replace(/\\s*\\(\\d+\\)\\s*$/,'').trim();
    }}

    function renderMeta(pgn,s){{
      const dl=document.getElementById('meta');
      const tags={{}};
      (pgn||'').split('\\n').forEach(line=>{{
        const m=line.match(/^\\[(\\w+)\\s+"(.*)"\\]/);
        if(m)tags[m[1]]=m[2];
      }});
      const opponentName=nameWithoutElo(s.opponent_label||s.engine_label)||tags.EngineName||s.engine_name||'Opponent';
      const model=s.model_display_name||s.model_name||'Agent';
      let whiteName='',blackName='',whiteElo=null,blackElo=null;
      if(s.agent_color==='WHITE'){{
        whiteName=model;blackName=opponentName;
        whiteElo=s.agent_elo;blackElo=s.opponent_elo!=null?s.opponent_elo:s.engine_elo;
      }}else{{
        whiteName=opponentName;blackName=model;
        whiteElo=s.opponent_elo!=null?s.opponent_elo:s.engine_elo;blackElo=s.agent_elo;
      }}
      const rows=[
        ['Game ID',s.game_id||tags.GameId||'{game_id}'],
        ['Event',tags.Event],['Date',tags.Date],
        ['White',playerLine(whiteName,whiteElo)],
        ['Black',playerLine(blackName,blackElo)],
      ];
      dl.innerHTML=rows.filter(r=>r[1]!=null&&r[1]!=='').map(r=>'<dt>'+r[0]+'</dt><dd>'+r[1]+'</dd>').join('');
    }}

    function renderMoves(rows,plies){{
      const el=document.getElementById('mv');
      if(!rows||!rows.length){{el.innerHTML='<p style="color:var(--faint);margin:0">No moves yet.</p>';return}}
      const lastPly=plies||0;
      el.innerHTML=rows.map(r=>{{
        const wOn=r.num*2-1===lastPly,bOn=r.num*2===lastPly;
        return '<div class="move-row"><span class="mn">'+r.num+'.</span>'
          +'<span class="w'+(wOn?' on':'')+'">'+r.white+'</span>'
          +'<span class="b'+(bOn?' on':'')+'">'+(r.black||'')+'</span></div>';
      }}).join('');
      const on=el.querySelector('.on');
      if(on)on.scrollIntoView({{block:'nearest'}});
    }}

    function hint(msg){{const h=document.getElementById('action-hint');if(h){{h.textContent=msg;setTimeout(()=>{{if(h.textContent===msg)h.textContent='';}},2000);}}}}

    document.getElementById('copy-pgn').onclick=()=>{{
      if(!lastPgn)return hint('PGN not loaded yet');
      navigator.clipboard.writeText(lastPgn).then(()=>hint('PGN copied'));
    }};

    async function u(){{
      try{{
        const s=await(await fetch('/api/games/{game_id}/state?debug=1')).json();
        const e=await(await fetch('/api/games/{game_id}/eval')).json();
        const ev=(e.ok&&e.eval_ui)?e.eval_ui:(s.eval_ui||null);
        if(ev)setLabels(ev,s);
        else renderGameState(s,null);
        const rev=s.revision||'';
        const plies=s.move_count!=null?s.move_count:(s.moves?s.moves.length:0);
        if(rev!==lastRevision||plies!==lastMoveCount){{
          lastRevision=rev;lastMoveCount=plies;
          if(s.move_rows)renderMoves(s.move_rows,plies);
          document.getElementById('board').src='/g/{game_id}/board.png?v='+rev;
        }}
        const p=await(await fetch('/api/games/{game_id}/pgn?debug=1')).json();
        if(p.pgn)lastPgn=p.pgn;
        renderMeta(lastPgn,s);
        syncHeights();
        if(s.game_over && pollTimer){{clearInterval(pollTimer);pollTimer=null;}}
      }}catch(e){{}}
    }}
    document.getElementById('board').onload=syncHeights;
    window.addEventListener('resize',syncHeights);
    let pollTimer=setInterval(u,3000);
    u();
    </script>
    {THEME_TOGGLE_SCRIPT}
    </body></html>"""
    return HTMLResponse(html)


@app.get("/g/{game_id}/board.png")
async def get_board_image(game_id: str):
    await asyncio.to_thread(_get_controller().refresh_board_image, game_id)
    board_path = game_manager.get_board_path(game_id)
    if not board_path.exists():
        raise HTTPException(404, "Board not found")
    return FileResponse(board_path, media_type="image/png")


@app.get("/api/games")
async def list_games(
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List games newest-first. status=in_progress|finished; omit for all."""
    await asyncio.to_thread(_get_game_service().prune_idle_games)
    games = game_manager.list_games()
    if status in ("in_progress", "active"):
        games = [g for g in games if g["state"].get("status") == "in_progress"]
    elif status in ("finished", "done", "completed"):
        games = [g for g in games if g["state"].get("status") != "in_progress"]

    total = len(games)
    if limit is not None:
        games = games[offset : offset + limit]
    else:
        games = games[offset:]

    enriched = []
    for g in games:
        state = g["state"]
        revision = BoardController.game_revision(state)
        elo_delta = None
        active_card = None
        agent_outcome = None
        if state.get("status") != "in_progress":
            elo_delta = _format_elo_change(_game_elo_change(state, g["game_id"]), state)
            agent_outcome = BoardController.agent_outcome(
                state["agent_color"], state.get("result")
            )
        else:
            active_card = _active_card(state, g["game_id"])
        enriched.append(
            {
                "game_id": g["game_id"],
                "revision": revision,
                "status": state.get("status"),
                "result": state.get("result"),
                "summary": _game_summary(state),
                "elo_change": elo_delta,
                "agent_outcome": agent_outcome,
                "active_card": active_card,
                "turn": active_card["turn_label"] if active_card else (
                    _get_controller().format_spectator_summary(state).split(" — ", 1)[-1]
                    if state.get("status") == "in_progress"
                    else state.get("result") or "done"
                ),
            }
        )
    return {
        "games": enriched,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@app.get("/api/games/{game_id}/state")
async def get_game_state(game_id: str, debug: Optional[str] = None):
    state = game_manager.load_state(game_id)
    if not state:
        raise HTTPException(404, "Game not found")
    delta = _game_elo_change(state, game_id)
    persp = _get_controller()._perspective(chess.Board(state["board_fen"]), state["agent_color"])
    labels = BoardController.side_labels(state)
    score_white = _resolve_eval_cp(state, game_id)
    outcome = BoardController.agent_outcome(state["agent_color"], state.get("result"))
    ctrl = _get_controller()
    end_reason_label = ctrl.resolve_end_reason(state, game_id) if state.get("status") != "in_progress" else None
    pgn_headers = state.get("pgn_headers") or {}
    engine_name = pgn_headers.get("EngineName", "Stockfish 17.1")
    engine_label = BoardController.engine_display_label(state)
    board_path = str(game_manager.get_board_path(game_id))
    agent_elo = (
        delta["elo_after"]
        if delta
        else round(_ladder().get_rating(state["model_name"]))
        if state.get("model_name")
        else None
    )
    game_over = state.get("status") != "in_progress" or persp.get("game_over")

    if debug_state_enabled(debug):
        return {
            **state,
            "revision": BoardController.game_revision(state),
            "summary": _game_summary(state),
            "elo_change": _format_elo_change(delta, state),
            "end_reason_label": end_reason_label,
            "engine_name": engine_name,
            "engine_label": engine_label,
            "agent_outcome": outcome if state.get("status") != "in_progress" else None,
            "move_rows": _move_rows(state),
            "eval_ui": _eval_ui(score_white, labels, state["agent_color"]),
            "agent_elo": agent_elo,
            "engine_elo": state.get("opponent_elo"),
            "game_over": game_over,
            "move_count": len(state.get("moves", [])),
            "board_path": board_path,
        }

    return agent_safe_spectator_state(
        state,
        revision=BoardController.game_revision(state),
        summary=_game_summary(state),
        elo_change=_format_elo_change(delta, state),
        end_reason_label=end_reason_label,
        engine_label=engine_label,
        agent_outcome=outcome if state.get("status") != "in_progress" else None,
        eval_ui=_eval_ui(score_white, labels, state["agent_color"]),
        agent_elo=agent_elo,
        engine_elo=state.get("opponent_elo"),
        game_over=game_over,
        board_path=board_path,
    )


@app.get("/api/games/{game_id}/pgn")
async def get_game_pgn(game_id: str, debug: Optional[str] = None):
    if not debug_state_enabled(debug):
        state = game_manager.load_state(game_id)
        if state and state.get("status") == "in_progress":
            raise HTTPException(
                403,
                "PGN available after the game ends. Enable CHESS_HARNESS_DEBUG for operator access.",
            )
    pgn_path = game_manager.get_pgn_path(game_id)
    if pgn_path.exists():
        return {"pgn": _get_controller()._clean_pgn(pgn_path.read_text(encoding="utf-8"))}
    result = _get_game_service().export_pgn(
        game_id, allow_in_progress=debug_state_enabled(debug)
    )
    if not result["ok"]:
        raise HTTPException(404, result["error"])
    return {"pgn": result["pgn"]}


@app.get("/api/games/{game_id}/eval")
async def get_eval(game_id: str):
    state = game_manager.load_state(game_id)
    if not state:
        raise HTTPException(404, "Game not found")
    if state["status"] != "in_progress":
        score = _resolve_eval_cp(state, game_id)
        labels = BoardController.side_labels(state)
        return {
            "ok": True,
            "score": score if score is not None else 0,
            "eval_ui": _eval_ui(score, labels, state["agent_color"]),
            "final": True,
        }
    try:
        score = _resolve_eval_cp(state, game_id)
        labels = BoardController.side_labels(state)
        return {
            "ok": True,
            "score": score if score is not None else 0,
            "eval_ui": _eval_ui(score, labels, state["agent_color"]),
        }
    except Exception:
        return {"ok": False, "score": 0}


def start_spectator(host: str = "127.0.0.1", port: int = 8765):
    import uvicorn

    uvicorn.run(app, host=host, port=port)
