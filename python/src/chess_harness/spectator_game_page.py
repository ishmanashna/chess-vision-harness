"""Spectator game view HTML for /g/{game_id} with validated, escaped output."""

from __future__ import annotations

import html
import json

from .ladder_display import FAVICON_LINKS, PUBLIC_SITE_HEADER, THEME_INIT_SCRIPT

__all__ = ["render_game_view_page"]


def render_game_view_page(game_id: str) -> str:
    """Return spectator game HTML. Caller must validate game_id first."""
    gid = html.escape(game_id, quote=True)
    gid_js = json.dumps(game_id)
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
    {FAVICON_LINKS}
    <title>{gid} · Chess Vision Harness</title>
    {THEME_INIT_SCRIPT}
    <link rel="stylesheet" href="/css/site.css"/>
    <style>
    .layout{{display:grid;grid-template-columns:minmax(280px,360px) max-content minmax(200px,280px);gap:16px;align-items:start;justify-content:center;width:fit-content;max-width:100%;margin:0 auto}}
    .col h2{{margin:0 0 12px;font-size:.7em;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--faint)}}
    .info-col{{display:flex;flex-direction:column;gap:12px}}
    .info-col-head{{display:flex;align-items:center;justify-content:flex-end;gap:10px;min-height:1.5rem}}
    .info-col-head:has(#info-panel-toggle[hidden]){{display:none}}
    .info-panel-toggle{{background:none;border:1px solid var(--border);border-radius:6px;padding:4px 10px;font:inherit;font-size:.78rem;font-weight:600;color:var(--text-secondary);cursor:pointer}}
    .info-panel-toggle:hover{{color:var(--text);border-color:var(--border-strong)}}
    .info-panel-toggle[hidden]{{display:none}}
    .info-card{{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:18px 20px}}
    .info-card h2{{margin:0 0 10px;font-size:.7em;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--faint)}}
    .info-panel-slot{{position:relative}}
    .info-stack{{display:flex;flex-direction:column;gap:16px}}
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
    .meta-grid{{display:grid;grid-template-columns:auto minmax(0,1fr);gap:6px 14px;font-size:.86em;line-height:1.45}}
    .meta-grid dt{{color:var(--faint);margin:0}}
    .meta-grid dd{{margin:0;color:var(--text-secondary);overflow-wrap:break-word;word-break:normal;min-width:0}}
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
    #board{{display:block;background:var(--surface);width:min(600px,calc(100vh - 220px),calc(100vw - 768px));height:auto}}
    .moves-col{{display:flex;flex-direction:column;min-height:0;max-height:calc(100vh - 140px)}}
    .moves-col .panel{{background:var(--surface);border:1px solid var(--border);border-radius:8px;display:flex;flex-direction:column;flex:1;min-height:200px;overflow:hidden}}
    .moves-col .panel h2{{padding:14px 16px 0;margin:0}}
    .moves-scroll{{overflow-y:auto;flex:1;padding:8px 12px 14px}}
    .move-row{{display:grid;grid-template-columns:26px 1fr 1fr;gap:8px;padding:7px 4px;font-size:.88em;border-bottom:1px solid var(--row)}}
    .move-row:last-child{{border-bottom:none}}
    .move-row .mn{{color:var(--faint);text-align:right;font-size:.82em}}
    .move-row .w.on,.move-row .b.on{{font-weight:700}}
    @media(max-width:960px){{
      .layout{{grid-template-columns:1fr;gap:20px;width:100%;justify-content:stretch}}
      .moves-col{{max-height:320px}}
      #board{{width:100%;max-width:480px}}
    }}
    </style></head><body class="game-view">
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
                <dt id="state-acc-white-label" class="quality-row" style="display:none">White accuracy</dt><dd id="state-acc-white" class="quality-row" style="display:none">—</dd>
                <dt id="state-pr-white-label" class="quality-row" style="display:none" title="Estimated strength from move accuracy — not ladder Elo.">White Estimated Elo</dt><dd id="state-pr-white" class="quality-row" style="display:none" title="Estimated strength from move accuracy — not ladder Elo.">—</dd>
                <dt id="state-acc-black-label" class="quality-row" style="display:none">Black accuracy</dt><dd id="state-acc-black" class="quality-row" style="display:none">—</dd>
                <dt id="state-pr-black-label" class="quality-row" style="display:none" title="Estimated strength from move accuracy — not ladder Elo.">Black Estimated Elo</dt><dd id="state-pr-black" class="quality-row" style="display:none" title="Estimated strength from move accuracy — not ladder Elo.">—</dd>
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
            <img id="board" src="/g/{gid}/board.png" alt="chess board"/>
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
    <script>
    const GAME_ID={gid_js};
    let lastRevision='';
    let lastMoveCount=0;
    let lastPgn='';
    const QUALITY_POLL_MAX=40;
    let qualityWaitAttempts=0;
    const PLAY_RATING_TIP='Estimated strength from move accuracy — not ladder Elo.';
    let chatSince=0;
    let chatPanelMode='info'; // 'info' | 'chat'
    let isAvhGame=false;

    function escHtml(s){{
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }}

    function setInfoPanelMode(mode){{
      chatPanelMode=mode==='chat'?'chat':'info';
      const stack=document.getElementById('info-stack');
      const chatPanel=document.getElementById('spec-chat-panel');
      const toggle=document.getElementById('info-panel-toggle');
      if(stack)stack.classList.toggle('is-covered',chatPanelMode==='chat');
      if(chatPanel)chatPanel.hidden=chatPanelMode!=='chat';
      if(toggle){{
        toggle.hidden=!isAvhGame;
        toggle.textContent=chatPanelMode==='chat'?'Show game':'Show chat';
      }}
    }}

    function appendChatMessages(messages){{
      const log=document.getElementById('spec-chat-log');
      if(!log||!messages||!messages.length)return;
      const frag=document.createDocumentFragment();
      messages.forEach(msg=>{{
        const row=document.createElement('div');
        const kind=msg.from==='agent'?'agent':'human';
        row.className='spec-chat-msg is-'+kind;
        const who=document.createElement('span');
        who.className='spec-chat-who';
        who.textContent=msg.from_label||(kind==='agent'?'Agent':'Human');
        const text=document.createElement('span');
        text.className='spec-chat-text';
        text.textContent=msg.text||'';
        row.appendChild(who);
        row.appendChild(text);
        frag.appendChild(row);
        if(msg.seq!=null)chatSince=Math.max(chatSince,Number(msg.seq)||0);
      }});
      log.appendChild(frag);
      log.scrollTop=log.scrollHeight;
    }}

    async function pollChat(){{
      if(!isAvhGame)return;
      try{{
        const r=await fetch('/api/games/'+encodeURIComponent(GAME_ID)+'/chat?since='+chatSince);
        if(!r.ok)return;
        const data=await r.json();
        if(data&&data.ok&&data.messages)appendChatMessages(data.messages);
      }}catch(e){{}}
    }}

    function syncAvhChatUi(s){{
      const wasAvh=isAvhGame;
      isAvhGame=s.game_type==='human_vs_agent';
      const toggle=document.getElementById('info-panel-toggle');
      if(toggle)toggle.hidden=!isAvhGame;
      if(!isAvhGame&&chatPanelMode==='chat')setInfoPanelMode('info');
      else if(isAvhGame&&!wasAvh)setInfoPanelMode(chatPanelMode);
      else if(toggle)toggle.textContent=chatPanelMode==='chat'?'Show game':'Show chat';
    }}

    function syncHeights(){{
      const board=document.getElementById('board');
      const track=document.getElementById('eval-track');
      const movesCol=document.getElementById('moves-col');
      const stack=document.querySelector('.board-stack');
      if(board&&track&&board.offsetHeight)track.style.height=board.offsetHeight+'px';
      if(stack&&movesCol)movesCol.style.maxHeight=stack.offsetHeight+'px';
    }}

    function formatAccuracy(v){{
      if(v==null||v==='')return'—';
      return String(v)+'%';
    }}

    function formatPlayRating(v){{
      if(v==null||v==='')return'—';
      return String(Math.round(v));
    }}

    function sideNamesFromState(s, tags){{
      tags=tags||{{}};
      let whiteName='',blackName='';
      if(s.game_type==='agent_vs_agent'){{
        whiteName=s.white_display_name||tags.White||'White';
        blackName=s.black_display_name||tags.Black||'Black';
      }}else if(s.game_type==='human_vs_agent'){{
        whiteName=s.white_display_name||tags.White||'White';
        blackName=s.black_display_name||tags.Black||'Black';
      }}else{{
        const opponentName=nameWithoutElo(s.opponent_label||s.engine_label)||tags.EngineName||s.engine_name||'Opponent';
        const model=s.model_display_name||s.model_name||'Agent';
        if(s.agent_color==='WHITE'){{
          whiteName=model;blackName=opponentName;
        }}else{{
          whiteName=opponentName;blackName=model;
        }}
      }}
      return {{whiteName,blackName}};
    }}

    function hasQualityMetrics(s){{
      return s.white_accuracy!=null||s.black_accuracy!=null||s.agent_accuracy!=null
        ||s.white_play_rating!=null||s.black_play_rating!=null||s.agent_play_rating!=null;
    }}

    function isQualityPending(s){{
      return s.game_over&&!s.quality_at&&s.result&&s.result!=='*'&&!hasQualityMetrics(s);
    }}

    function renderQualityMetrics(s, tags){{
      const pending=isQualityPending(s);
      const show=hasQualityMetrics(s)||pending||(s.game_over&&s.result&&s.result!=='*');
      const rows=document.querySelectorAll('.quality-row');
      rows.forEach(el=>{{el.style.display=show?'':'none';}});
      if(!show)return;
      const {{whiteName,blackName}}=sideNamesFromState(s, tags);
      const wAccLbl=document.getElementById('state-acc-white-label');
      const bAccLbl=document.getElementById('state-acc-black-label');
      const wPrLbl=document.getElementById('state-pr-white-label');
      const bPrLbl=document.getElementById('state-pr-black-label');
      if(wAccLbl)wAccLbl.textContent=whiteName+' accuracy';
      if(bAccLbl)bAccLbl.textContent=blackName+' accuracy';
      if(wPrLbl){{wPrLbl.textContent=whiteName+' Estimated Elo';wPrLbl.title=PLAY_RATING_TIP;}}
      if(bPrLbl){{bPrLbl.textContent=blackName+' Estimated Elo';bPrLbl.title=PLAY_RATING_TIP;}}
      const accWhite=document.getElementById('state-acc-white');
      const accBlack=document.getElementById('state-acc-black');
      const prWhite=document.getElementById('state-pr-white');
      const prBlack=document.getElementById('state-pr-black');
      let wAcc=s.white_accuracy,bAcc=s.black_accuracy,wPr=s.white_play_rating,bPr=s.black_play_rating;
      if(wAcc==null&&bAcc==null&&s.agent_accuracy!=null){{
        if(s.agent_color==='WHITE')wAcc=s.agent_accuracy;
        else bAcc=s.agent_accuracy;
      }}
      if(wPr==null&&bPr==null&&s.agent_play_rating!=null){{
        if(s.agent_color==='WHITE')wPr=s.agent_play_rating;
        else bPr=s.agent_play_rating;
      }}
      const valueEls=[accWhite,accBlack,prWhite,prBlack];
      if(pending){{
        valueEls.forEach(el=>{{
          if(!el)return;
          el.textContent='Analysing…';
          el.classList.add('quality-pending');
        }});
        return;
      }}
      valueEls.forEach(el=>{{if(el)el.classList.remove('quality-pending');}});
      if(accWhite)accWhite.textContent=formatAccuracy(wAcc);
      if(accBlack)accBlack.textContent=formatAccuracy(bAcc);
      if(prWhite){{prWhite.textContent=formatPlayRating(wPr);prWhite.title=PLAY_RATING_TIP;}}
      if(prBlack){{prBlack.textContent=formatPlayRating(bPr);prBlack.title=PLAY_RATING_TIP;}}
    }}

    function shouldKeepPolling(s){{
      if(!s.game_over)return true;
      if(s.quality_at)return false;
      if(s.result==='*')return false;
      return qualityWaitAttempts<QUALITY_POLL_MAX;
    }}

    function playerLine(name,elo){{
      if(elo==null)return name;
      return name+' ('+elo+')';
    }}

    function renderGameState(s,ev){{
      const result=document.getElementById('state-result');
      const term=document.getElementById('state-termination');
      const evalEl=document.getElementById('state-eval');
      const evalLabel=document.getElementById('state-eval-label');
      const eloEl=document.getElementById('state-elo');
      const eloLabel=document.getElementById('state-elo-label');
      const showEval=s.show_eval!==false;
      const showElo=showEval&&s.game_type!=='human_vs_agent';
      const evalCol=document.getElementById('eval-col');
      if(evalCol)evalCol.style.display=showEval?'':'none';
      if(evalLabel)evalLabel.style.display=showEval?'':'none';
      if(evalEl)evalEl.style.display=showEval?'':'none';
      if(eloLabel)eloLabel.style.display=showElo?'':'none';
      if(eloEl)eloEl.style.display=showElo?'':'none';
      if(result)result.textContent=s.game_over?(s.result||'—'):'In progress';
      if(term)term.textContent=s.end_reason_label||'—';
      if(evalEl&&showEval){{
        const t=ev&&ev.text&&ev.text!=='—'?ev.text:'—';
        evalEl.textContent=t;
      }}
      if(eloEl&&showElo)eloEl.textContent=s.elo_change||'No ELO change recorded yet.';
    }}

    function setLabels(ev,s){{
      const showEval=s.show_eval!==false;
      if(ev&&showEval){{
        document.getElementById('lbl-black').textContent=ev.top_label||ev.black_label||'Black';
        document.getElementById('lbl-white').textContent=ev.bottom_label||ev.white_label||'White';
        const bar=document.getElementById('eval-black');
        bar.style.height=ev.black_pct||'50%';
        if(ev.black_at_bottom){{bar.style.top='auto';bar.style.bottom='0';}}
        else{{bar.style.top='0';bar.style.bottom='auto';}}
      }}else if(s.white_display_name||s.black_display_name){{
        document.getElementById('lbl-black').textContent=s.black_display_name||'Black';
        document.getElementById('lbl-white').textContent=s.white_display_name||'White';
      }}
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
      let whiteName='',blackName='',whiteElo=null,blackElo=null;
      if(s.game_type==='agent_vs_agent'){{
        whiteName=s.white_display_name||tags.White||'White';
        blackName=s.black_display_name||tags.Black||'Black';
        whiteElo=s.white_elo;blackElo=s.black_elo;
      }}else if(s.game_type==='human_vs_agent'){{
        whiteName=s.white_display_name||tags.White||'White';
        blackName=s.black_display_name||tags.Black||'Black';
        if(s.agent_color==='WHITE'){{whiteElo=s.agent_elo;blackElo=null;}}
        else{{whiteElo=null;blackElo=s.agent_elo;}}
      }}else{{
        const opponentName=nameWithoutElo(s.opponent_label||s.engine_label)||tags.EngineName||s.engine_name||'Opponent';
        const model=s.model_display_name||s.model_name||'Agent';
        if(s.agent_color==='WHITE'){{
          whiteName=model;blackName=opponentName;
          whiteElo=s.agent_elo;blackElo=s.opponent_elo!=null?s.opponent_elo:s.engine_elo;
        }}else{{
          whiteName=opponentName;blackName=model;
          whiteElo=s.opponent_elo!=null?s.opponent_elo:s.engine_elo;blackElo=s.agent_elo;
        }}
      }}
      const rows=[
        ['Game ID',s.game_id||tags.GameId||GAME_ID],
        ['Event',tags.Event],['Date',tags.Date],
        ['White',playerLine(whiteName,whiteElo)],
        ['Black',playerLine(blackName,blackElo)],
      ];
      if(s.game_type==='agent_vs_agent')rows.splice(1,0,['Type','Agent vs agent']);
      if(s.game_type==='human_vs_agent')rows.splice(1,0,['Type','Agent vs human (unranked)']);
      dl.innerHTML=rows.filter(r=>r[1]!=null&&r[1]!=='').map(r=>'<dt>'+escHtml(r[0])+'</dt><dd>'+escHtml(r[1])+'</dd>').join('');
      renderQualityMetrics(s, tags);
    }}

    function renderMoves(rows,plies){{
      const el=document.getElementById('mv');
      if(!rows||!rows.length){{el.innerHTML='<p style="color:var(--faint);margin:0">No moves yet.</p>';return}}
      const lastPly=plies||0;
      el.innerHTML=rows.map(r=>{{
        const wOn=r.num*2-1===lastPly,bOn=r.num*2===lastPly;
        return '<div class="move-row"><span class="mn">'+escHtml(r.num)+'.</span>'
          +'<span class="w'+(wOn?' on':'')+'">'+escHtml(r.white)+'</span>'
          +'<span class="b'+(bOn?' on':'')+'">'+escHtml(r.black||'')+'</span></div>';
      }}).join('');
      const on=el.querySelector('.on');
      if(on)on.scrollIntoView({{block:'nearest'}});
    }}

    function hint(msg){{const h=document.getElementById('action-hint');if(h){{h.textContent=msg;setTimeout(()=>{{if(h.textContent===msg)h.textContent='';}},2000);}}}}

    document.getElementById('copy-pgn').onclick=()=>{{
      if(!lastPgn)return hint('PGN not loaded yet');
      navigator.clipboard.writeText(lastPgn).then(()=>hint('PGN copied'));
    }};

    const panelToggle=document.getElementById('info-panel-toggle');
    if(panelToggle){{
      panelToggle.onclick=()=>{{
        setInfoPanelMode(chatPanelMode==='chat'?'info':'chat');
        if(chatPanelMode==='chat')pollChat();
      }};
    }}

    async function u(){{
      try{{
        const s=await(await fetch('/api/games/'+encodeURIComponent(GAME_ID)+'/state')).json();
        syncAvhChatUi(s);
        const e=await(await fetch('/api/games/'+encodeURIComponent(GAME_ID)+'/eval')).json();
        const showEval=s.show_eval!==false&&e.show_eval!==false;
        const ev=showEval&&e.ok&&e.eval_ui?e.eval_ui:(showEval?s.eval_ui||null:null);
        if(ev)setLabels(ev,s);
        else setLabels(null,s);
        const rev=s.revision||'';
        const plies=s.move_count!=null?s.move_count:0;
        if(rev!==lastRevision||plies!==lastMoveCount){{
          lastRevision=rev;lastMoveCount=plies;
          const m=await(await fetch('/api/games/'+encodeURIComponent(GAME_ID)+'/moves')).json();
          if(m.move_rows)renderMoves(m.move_rows,plies);
          document.getElementById('board').src='/g/'+encodeURIComponent(GAME_ID)+'/board.png?v='+encodeURIComponent(rev);
        }}
        const p=await(await fetch('/api/games/'+encodeURIComponent(GAME_ID)+'/pgn')).json();
        if(p.pgn)lastPgn=p.pgn;
        renderMeta(lastPgn,s);
        if(isAvhGame)await pollChat();
        syncHeights();
        if(s.game_over&&!s.quality_at&&s.result!=='*'&&qualityWaitAttempts<QUALITY_POLL_MAX)qualityWaitAttempts++;
        if(!shouldKeepPolling(s)&&pollTimer){{clearInterval(pollTimer);pollTimer=null;}}
      }}catch(e){{}}
    }}
    document.getElementById('board').onload=syncHeights;
    window.addEventListener('resize',syncHeights);
    let pollTimer=setInterval(u,3000);
    u();
    </script>
    <script src="/js/common.js"></script>
    </body></html>"""
