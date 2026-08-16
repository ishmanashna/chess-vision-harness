/**
 * Spectator game page (/g/{id}) — poll state, moves, eval, chat; drive cm-chessboard.
 */

import { createSpectatorBoard } from "./spectator-board.js";

const QUALITY_POLL_MAX = 40;
const PLAY_RATING_TIP =
  "Estimated strength from move accuracy via the calibration accuracy→Elo table — not ladder Elo.";

function gameIdFromPage() {
  const root = document.body;
  const fromData = root && root.dataset ? root.dataset.gameId : "";
  if (fromData) return fromData;
  const parts = window.location.pathname.replace(/\/+$/, "").split("/");
  const idx = parts.indexOf("g");
  const id = idx >= 0 ? parts[idx + 1] : "";
  // Bare /g/ must not be treated as id "g" (Pages once redirected /g/{id} → /g/).
  if (!id || id === "index.html") return "";
  return id;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function abbreviateName(value) {
  if (window.CVH && typeof window.CVH.abbreviateListName === "function") {
    return window.CVH.abbreviateListName(value);
  }
  return String(value || "");
}

function syncHeights() {
  if (window.CVH && typeof window.CVH.syncWatchHeights === "function") {
    window.CVH.syncWatchHeights();
    return;
  }
  const wrap = document.getElementById("board-wrap") || document.getElementById("board");
  const track = document.getElementById("eval-track");
  const movesCol = document.getElementById("moves-col");
  const infoCol = document.querySelector(".info-col");
  const stack = document.querySelector(".board-stack");
  if (wrap && track && wrap.offsetHeight) {
    track.style.height = wrap.offsetHeight + "px";
  }
  if (stack && stack.offsetHeight) {
    const h = stack.offsetHeight + "px";
    if (movesCol) movesCol.style.maxHeight = h;
    if (infoCol) infoCol.style.height = h;
  }
}

function showPollError(message) {
  if (window.CVH && typeof window.CVH.showWatchPollError === "function") {
    window.CVH.showWatchPollError(message);
  }
}

function wireGameShellChrome(gameId) {
  document.title = gameId + " · Chess Vision Harness";
  const dl = document.querySelector("[data-board-download]");
  if (dl) {
    dl.href = "/g/" + encodeURIComponent(gameId) + "/board.png";
    dl.setAttribute("download", gameId + "-board.png");
  }
}

async function main() {
  const GAME_ID = gameIdFromPage();
  if (!GAME_ID) return;
  wireGameShellChrome(GAME_ID);

  const mount = document.getElementById("board");
  if (!mount) return;

  const board = createSpectatorBoard(mount);
  // Phase 7: window board.setViewPly(n) when scrubbing; syncTip always snaps to tip on new moves.
  window.CVH = window.CVH || {};
  window.CVH.spectatorBoard = board;

  let lastRevision = "";
  let lastMoveCount = 0;
  let lastPgn = "";
  let lastMoveRows = null;
  let lastState = null;
  let selectedPly = 0;
  let qualityWaitAttempts = 0;
  let chatSince = 0;
  let chatPanelMode = "info";
  let isAvhGame = false;
  let pollTimer = null;
  let evalDebounceTimer = null;
  let evalFetchGen = 0;
  const EVAL_DEBOUNCE_MS = 150;

  function setInfoPanelMode(mode) {
    chatPanelMode = mode === "chat" ? "chat" : "info";
    const stack = document.getElementById("info-stack");
    const chatPanel = document.getElementById("spec-chat-panel");
    const toggleInfo = document.getElementById("info-panel-toggle");
    const toggleChat = document.getElementById("info-panel-toggle-chat");
    if (stack) stack.classList.toggle("is-covered", chatPanelMode === "chat");
    if (chatPanel) chatPanel.hidden = chatPanelMode !== "chat";
    // Keep a visible control outside the covered info stack so chat is not a dead end.
    if (toggleInfo) {
      toggleInfo.hidden = !isAvhGame || chatPanelMode === "chat";
      toggleInfo.textContent = "Show chat";
    }
    if (toggleChat) {
      toggleChat.hidden = !isAvhGame || chatPanelMode !== "chat";
      toggleChat.textContent = "Show game";
    }
  }

  function appendChatMessages(messages) {
    const log = document.getElementById("spec-chat-log");
    if (!log || !messages || !messages.length) return;
    const frag = document.createDocumentFragment();
    messages.forEach((msg) => {
      const row = document.createElement("div");
      const kind = msg.from === "agent" ? "agent" : "human";
      row.className = "spec-chat-msg is-" + kind;
      const who = document.createElement("span");
      who.className = "spec-chat-who";
      who.textContent =
        msg.from_label || (kind === "agent" ? "Agent" : "Human");
      const text = document.createElement("span");
      text.className = "spec-chat-text";
      text.textContent = msg.text || "";
      row.appendChild(who);
      row.appendChild(text);
      frag.appendChild(row);
      if (msg.seq != null) chatSince = Math.max(chatSince, Number(msg.seq) || 0);
    });
    log.appendChild(frag);
    log.scrollTop = log.scrollHeight;
  }

  async function pollChat() {
    if (!isAvhGame) return;
    try {
      const r = await fetch(
        "/api/games/" + encodeURIComponent(GAME_ID) + "/chat?since=" + chatSince
      );
      if (!r.ok) return;
      const data = await r.json();
      if (data && data.ok && data.messages) appendChatMessages(data.messages);
    } catch (e) {
      /* ignore */
    }
  }

  function syncAvhChatUi(s) {
    const wasAvh = isAvhGame;
    isAvhGame = s.game_type === "human_vs_agent";
    if (!isAvhGame && chatPanelMode === "chat") setInfoPanelMode("info");
    else if (isAvhGame && !wasAvh) setInfoPanelMode(chatPanelMode);
    else setInfoPanelMode(chatPanelMode);
  }

  function formatAccuracy(v) {
    if (v == null || v === "") return "—";
    return String(v) + "%";
  }

  function formatPlayRating(v) {
    if (v == null || v === "") return "—";
    return String(Math.round(v));
  }

  function sideNamesFromState(s, tags) {
    tags = tags || {};
    let whiteName = "",
      blackName = "";
    if (s.game_type === "agent_vs_agent") {
      whiteName = s.white_display_name || tags.White || "White";
      blackName = s.black_display_name || tags.Black || "Black";
    } else if (s.game_type === "human_vs_agent") {
      whiteName = s.white_display_name || tags.White || "White";
      blackName = s.black_display_name || tags.Black || "Black";
    } else {
      const opponentName =
        nameWithoutElo(s.opponent_label || s.engine_label) ||
        tags.EngineName ||
        s.engine_name ||
        "Opponent";
      const model = s.model_display_name || s.model_name || "Agent";
      if (s.agent_color === "WHITE") {
        whiteName = model;
        blackName = opponentName;
      } else {
        whiteName = opponentName;
        blackName = model;
      }
    }
    return {
      whiteName: abbreviateName(whiteName),
      blackName: abbreviateName(blackName),
    };
  }

  function hasQualityMetrics(s) {
    return (
      s.white_accuracy != null ||
      s.black_accuracy != null ||
      s.agent_accuracy != null ||
      s.white_play_rating != null ||
      s.black_play_rating != null ||
      s.agent_play_rating != null
    );
  }

  function isQualityPending(s) {
    return (
      s.game_over &&
      !s.quality_at &&
      s.result &&
      s.result !== "*" &&
      !hasQualityMetrics(s)
    );
  }

  function renderQualityMetrics(s, tags) {
    const pending = isQualityPending(s);
    const show =
      hasQualityMetrics(s) || pending || (s.game_over && s.result && s.result !== "*");
    const rows = document.querySelectorAll(".quality-row");
    rows.forEach((el) => {
      el.hidden = !show;
    });
    if (!show) return;
    const wAccLbl = document.getElementById("state-acc-white-label");
    const bAccLbl = document.getElementById("state-acc-black-label");
    const wPrLbl = document.getElementById("state-pr-white-label");
    const bPrLbl = document.getElementById("state-pr-black-label");
    if (wAccLbl) wAccLbl.textContent = "White accuracy";
    if (bAccLbl) bAccLbl.textContent = "Black accuracy";
    if (wPrLbl) {
      wPrLbl.textContent = "White Performance";
      wPrLbl.title = PLAY_RATING_TIP;
    }
    if (bPrLbl) {
      bPrLbl.textContent = "Black Performance";
      bPrLbl.title = PLAY_RATING_TIP;
    }
    const accWhite = document.getElementById("state-acc-white");
    const accBlack = document.getElementById("state-acc-black");
    const prWhite = document.getElementById("state-pr-white");
    const prBlack = document.getElementById("state-pr-black");
    let wAcc = s.white_accuracy,
      bAcc = s.black_accuracy,
      wPr = s.white_play_rating,
      bPr = s.black_play_rating;
    if (wAcc == null && bAcc == null && s.agent_accuracy != null) {
      if (s.agent_color === "WHITE") wAcc = s.agent_accuracy;
      else bAcc = s.agent_accuracy;
    }
    if (wPr == null && bPr == null && s.agent_play_rating != null) {
      if (s.agent_color === "WHITE") wPr = s.agent_play_rating;
      else bPr = s.agent_play_rating;
    }
    const valueEls = [accWhite, accBlack, prWhite, prBlack];
    if (pending) {
      valueEls.forEach((el) => {
        if (!el) return;
        el.textContent = "Analysing…";
        el.classList.add("quality-pending");
      });
      return;
    }
    valueEls.forEach((el) => {
      if (el) el.classList.remove("quality-pending");
    });
    if (accWhite) accWhite.textContent = formatAccuracy(wAcc);
    if (accBlack) accBlack.textContent = formatAccuracy(bAcc);
    if (prWhite) {
      prWhite.textContent = formatPlayRating(wPr);
      prWhite.title = PLAY_RATING_TIP;
    }
    if (prBlack) {
      prBlack.textContent = formatPlayRating(bPr);
      prBlack.title = PLAY_RATING_TIP;
    }
  }

  function shouldKeepPolling(s) {
    if (!s.game_over) return true;
    if (s.quality_at) return false;
    if (s.result === "*") return false;
    return qualityWaitAttempts < QUALITY_POLL_MAX;
  }

  function playerLine(name, elo) {
    if (elo == null) return name;
    return name + " (" + elo + ")";
  }

  function renderGameState(s, ev) {
    const result = document.getElementById("state-result");
    const term = document.getElementById("state-termination");
    const evalEl = document.getElementById("state-eval");
    const evalLabel = document.getElementById("state-eval-label");
    const eloEl = document.getElementById("state-elo");
    const eloLabel = document.getElementById("state-elo-label");
    const showEval = s.show_eval !== false;
    const showElo = showEval && s.game_type !== "human_vs_agent";
    const evalCol = document.getElementById("eval-col");
    if (evalCol) evalCol.style.display = showEval ? "" : "none";
    if (evalLabel) evalLabel.hidden = !showEval;
    if (evalEl) evalEl.hidden = !showEval;
    if (eloLabel) eloLabel.hidden = !showElo;
    if (eloEl) eloEl.hidden = !showElo;
    if (result) result.textContent = s.game_over ? s.result || "—" : "In progress";
    if (term) term.textContent = s.end_reason_label || "—";
    if (evalEl && showEval) {
      const t = ev && ev.text && ev.text !== "—" ? ev.text : "—";
      evalEl.textContent = t;
    }
    if (eloEl && showElo) eloEl.textContent = s.elo_change || "—";
  }

  function setLabels(ev, s) {
    const showEval = s.show_eval !== false;
    if (ev && showEval) {
      document.getElementById("lbl-black").textContent = abbreviateName(
        ev.top_label || ev.black_label || "Black"
      );
      document.getElementById("lbl-white").textContent = abbreviateName(
        ev.bottom_label || ev.white_label || "White"
      );
      const bar = document.getElementById("eval-black");
      bar.style.height = ev.black_pct || "50%";
      if (ev.black_at_bottom) {
        bar.style.top = "auto";
        bar.style.bottom = "0";
      } else {
        bar.style.top = "0";
        bar.style.bottom = "auto";
      }
    } else if (s.white_display_name || s.black_display_name) {
      document.getElementById("lbl-black").textContent = abbreviateName(
        s.black_display_name || "Black"
      );
      document.getElementById("lbl-white").textContent = abbreviateName(
        s.white_display_name || "White"
      );
    }
    renderGameState(s, ev);
  }

  function nameWithoutElo(name) {
    if (window.CVH && typeof window.CVH.nameWithoutElo === "function") {
      return window.CVH.nameWithoutElo(name);
    }
    if (!name) return "";
    return String(name).replace(/\s*\(\d+\)\s*$/, "").trim();
  }

  function renderMeta(pgn, s) {
    const dl = document.getElementById("meta");
    const tags = {};
    (pgn || "").split("\n").forEach((line) => {
      const m = line.match(/^\[(\w+)\s+"(.*)"\]/);
      if (m) tags[m[1]] = m[2];
    });
    let whiteName = "",
      blackName = "",
      whiteElo = null,
      blackElo = null;
    if (s.game_type === "agent_vs_agent") {
      whiteName = s.white_display_name || tags.White || "White";
      blackName = s.black_display_name || tags.Black || "Black";
      whiteElo = s.white_elo;
      blackElo = s.black_elo;
    } else if (s.game_type === "human_vs_agent") {
      whiteName = s.white_display_name || tags.White || "White";
      blackName = s.black_display_name || tags.Black || "Black";
      if (s.agent_color === "WHITE") {
        whiteElo = s.agent_elo;
        blackElo = null;
      } else {
        whiteElo = null;
        blackElo = s.agent_elo;
      }
    } else {
      const opponentName =
        nameWithoutElo(s.opponent_label || s.engine_label) ||
        tags.EngineName ||
        s.engine_name ||
        "Opponent";
      const model = s.model_display_name || s.model_name || "Agent";
      if (s.agent_color === "WHITE") {
        whiteName = model;
        blackName = opponentName;
        whiteElo = s.agent_elo;
        blackElo = s.opponent_elo != null ? s.opponent_elo : s.engine_elo;
      } else {
        whiteName = opponentName;
        blackName = model;
        whiteElo = s.opponent_elo != null ? s.opponent_elo : s.engine_elo;
        blackElo = s.agent_elo;
      }
    }
    whiteName = abbreviateName(whiteName);
    blackName = abbreviateName(blackName);
    const gameId = s.game_id || tags.GameId || GAME_ID;
    const dateLabel = formatSpectatorDate(s, tags);
    const rows = [
      ["Game ID", gameId, "game-id"],
      ["Event", tags.Event],
      ["Date", dateLabel],
      ["White", playerLine(whiteName, whiteElo)],
      ["Black", playerLine(blackName, blackElo)],
    ];
    if (s.game_type === "agent_vs_agent")
      rows.splice(1, 0, ["Type", "Agent vs agent"]);
    if (s.game_type === "human_vs_agent")
      rows.splice(1, 0, ["Type", "Agent vs Human"]);
    dl.innerHTML = rows
      .filter((r) => r[1] != null && r[1] !== "")
      .map((r) => {
        const kind = r[2];
        let dd;
        if (kind === "game-id") {
          dd =
            '<dd class="meta-game-id"><code title="' +
            escHtml(r[1]) +
            '">' +
            escHtml(r[1]) +
            "</code></dd>";
        } else {
          dd = "<dd>" + escHtml(r[1]) + "</dd>";
        }
        return "<dt>" + escHtml(r[0]) + "</dt>" + dd;
      })
      .join("");
    renderQualityMetrics(s, tags);
  }

  function formatSpectatorDate(s, tags) {
    const raw = s && s.last_activity;
    if (raw) {
      const ms = Date.parse(raw);
      if (Number.isFinite(ms)) {
        try {
          return new Intl.DateTimeFormat(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          }).format(new Date(ms));
        } catch (_) {
          return new Date(ms).toISOString().slice(0, 16).replace("T", " ");
        }
      }
    }
    return tags.Date || "";
  }

  function applyEvalResponse(e, s) {
    const showEval = s && s.show_eval !== false && e && e.show_eval !== false;
    const ev =
      showEval && e && e.ok && e.eval_ui
        ? e.eval_ui
        : showEval
          ? (s && s.eval_ui) || null
          : null;
    if (ev) setLabels(ev, s);
    else setLabels(null, s);
  }

  function evalFromState(s) {
    if (!s || s.show_eval === false) return null;
    return { ok: true, eval_ui: s.eval_ui, show_eval: s.show_eval };
  }

  function fetchEvalForPly(ply, immediate) {
    const tipPly = board.getTipPly();
    const n = Math.max(0, Math.min(Number(ply) || 0, tipPly));
    const atTip = n >= tipPly;
    const run = async () => {
      const gen = ++evalFetchGen;
      try {
        let url = "/api/games/" + encodeURIComponent(GAME_ID) + "/eval";
        if (!atTip) url += "?ply=" + n;
        const e = await (await fetch(url)).json();
        if (gen !== evalFetchGen) return;
        applyEvalResponse(e, lastState || {});
      } catch (_) {
        /* ignore */
      }
    };
    if (immediate) {
      if (evalDebounceTimer) {
        clearTimeout(evalDebounceTimer);
        evalDebounceTimer = null;
      }
      return run();
    }
    if (evalDebounceTimer) clearTimeout(evalDebounceTimer);
    evalDebounceTimer = setTimeout(() => {
      evalDebounceTimer = null;
      run();
    }, EVAL_DEBOUNCE_MS);
  }

  function scrubToPly(ply, animate) {
    const tipPly = board.getTipPly();
    const n = Math.max(0, Math.min(Number(ply) || 0, tipPly));
    selectedPly = n;
    board.setViewPly(n, animate);
    if (lastMoveRows) renderMoves(lastMoveRows, selectedPly);
    fetchEvalForPly(n, false);
  }

  function syncMovesScroll(el, viewPly, tipPly) {
    if (!el) return;
    const atTip = viewPly >= tipPly;
    const pinToBottom = () => {
      el.scrollTop = el.scrollHeight;
    };
    if (atTip) {
      pinToBottom();
      requestAnimationFrame(pinToBottom);
    } else {
      const on = el.querySelector(".on");
      if (on) on.scrollIntoView({ block: "center", inline: "nearest" });
    }
  }

  function renderMoves(rows, viewPly) {
    const el = document.getElementById("mv");
    lastMoveRows = rows;
    if (!rows || !rows.length) {
      el.innerHTML =
        '<p style="color:var(--faint);margin:0">No moves yet.</p>';
      return;
    }
    const sel = viewPly != null ? viewPly : selectedPly;
    const tipPly = board.getTipPly();
    el.innerHTML = rows
      .map((r) => {
        const wPly = r.num * 2 - 1;
        const bPly = r.num * 2;
        const wOn = wPly === sel;
        const bOn = bPly === sel;
        const black = r.black || "";
        return (
          '<div class="move-row"><span class="mn">' +
          escHtml(r.num) +
          '.</span><span class="w' +
          (wOn ? " on" : "") +
          '" data-ply="' +
          wPly +
          '">' +
          escHtml(r.white) +
          "</span>" +
          (black
            ? '<span class="b' +
              (bOn ? " on" : "") +
              '" data-ply="' +
              bPly +
              '">' +
              escHtml(black) +
              "</span>"
            : '<span class="b"></span>') +
          "</div>"
        );
      })
      .join("");
    el.querySelectorAll("[data-ply]").forEach((cell) => {
      cell.addEventListener("click", () => {
        const ply = Number(cell.getAttribute("data-ply"));
        if (!Number.isFinite(ply)) return;
        scrubToPly(ply, true);
      });
    });
    syncMovesScroll(el, sel, tipPly);
  }

  function hint(msg) {
    const h = document.getElementById("action-hint");
    if (h) {
      h.textContent = msg;
      setTimeout(() => {
        if (h.textContent === msg) h.textContent = "";
      }, 2000);
    }
  }

  document.getElementById("copy-pgn").onclick = () => {
    if (!lastPgn) return hint("PGN not loaded yet");
    navigator.clipboard.writeText(lastPgn).then(() => hint("PGN copied"));
  };

  const panelToggle = document.getElementById("info-panel-toggle");
  const panelToggleChat = document.getElementById("info-panel-toggle-chat");
  function onPanelToggle() {
    setInfoPanelMode(chatPanelMode === "chat" ? "info" : "chat");
    if (chatPanelMode === "chat") pollChat();
  }
  if (panelToggle) panelToggle.onclick = onPanelToggle;
  if (panelToggleChat) panelToggleChat.onclick = onPanelToggle;

  async function poll() {
    try {
      const s = await (
        await fetch("/api/games/" + encodeURIComponent(GAME_ID) + "/state")
      ).json();
      lastState = s;
      syncAvhChatUi(s);
      const rev = s.revision || "";
      const stateMoveCount =
        s.move_count != null && s.move_count !== ""
          ? Number(s.move_count)
          : null;
      const plies =
        stateMoveCount != null && Number.isFinite(stateMoveCount)
          ? stateMoveCount
          : 0;
      const moveIncreased = plies > lastMoveCount;
      const firstLoad = lastMoveRows === null;

      const m = await (
        await fetch("/api/games/" + encodeURIComponent(GAME_ID) + "/moves")
      ).json();
      const pliesDetail = Array.isArray(m.plies_detail) ? m.plies_detail : [];
      const movesPlyCount = pliesDetail.length;
      const effectiveMoveCount =
        stateMoveCount != null && Number.isFinite(stateMoveCount)
          ? stateMoveCount
          : movesPlyCount;
      const metaChanged =
        firstLoad ||
        rev !== lastRevision ||
        effectiveMoveCount !== lastMoveCount;
      const needsBoardSync =
        firstLoad ||
        moveIncreased ||
        movesPlyCount !== board.getTipPly();
      const animate = !firstLoad && moveIncreased && lastMoveCount > 0;

      if (metaChanged) {
        lastRevision = rev;
        lastMoveCount = effectiveMoveCount;
      }

      if (needsBoardSync) {
        await board.syncTip(m.start_fen, pliesDetail, animate);
        selectedPly = board.getTipPly();
        renderMoves(m.move_rows || [], selectedPly);
        applyEvalResponse(evalFromState(s), s);
        syncHeights();
      } else {
        renderMoves(m.move_rows || [], selectedPly);
        if (selectedPly >= board.getTipPly()) {
          applyEvalResponse(evalFromState(s), s);
        }
      }
      if (s.game_over) {
        const p = await (
          await fetch("/api/games/" + encodeURIComponent(GAME_ID) + "/pgn")
        ).json();
        if (p.pgn) lastPgn = p.pgn;
      }
      renderMeta(lastPgn, s);
      if (isAvhGame) await pollChat();
      syncHeights();
      if (selectedPly >= board.getTipPly()) {
        const mvEl = document.getElementById("mv");
        syncMovesScroll(mvEl, selectedPly, board.getTipPly());
      }
      if (
        s.game_over &&
        !s.quality_at &&
        s.result !== "*" &&
        qualityWaitAttempts < QUALITY_POLL_MAX
      ) {
        qualityWaitAttempts++;
      }
      if (!shouldKeepPolling(s) && pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      showPollError("");
    } catch (e) {
      showPollError("Could not refresh game state — is the server online?");
    }
  }

  window.addEventListener("resize", syncHeights);
  // ResizeObserver keeps eval bar aligned when cm-chessboard finishes layout.
  if (typeof ResizeObserver !== "undefined") {
    const wrap = document.getElementById("board-wrap");
    if (wrap) {
      const ro = new ResizeObserver(() => syncHeights());
      ro.observe(wrap);
    }
  }
  pollTimer = setInterval(poll, 3000);
  poll();
}

main();
