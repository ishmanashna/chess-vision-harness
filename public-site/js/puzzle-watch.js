/**
 * Public puzzle watch/replay page (/p/{id}).
 * Mirrors the game spectator layout: info column, board column, moves column.
 * Live state polls the observer-safe API and lists the agent's submitted moves
 * as SAN move rows; after the attempt ends the solution line replaces them
 * (first wrong move flagged). The info column shows the agent's current puzzle
 * metrics at all times and the attempt chain (same pseudonymous key); when the
 * agent starts the next puzzle the page auto-follows to it.
 */

import {
  Chessboard,
  COLOR,
  BORDER_TYPE,
} from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/Chessboard.js";

const BOARD_ASSETS =
  "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/assets/";
const POLL_MS = 3000;
const CHAIN_POLL_MS = 15000;
const FOLLOW_DELAY_MS = 5000;

function attemptIdFromPage() {
  const root = document.body;
  const fromData = root && root.dataset ? root.dataset.attemptId : "";
  if (fromData) return fromData;
  const parts = window.location.pathname.replace(/\/+$/, "").split("/");
  const idx = parts.indexOf("p");
  if (idx >= 0 && parts[idx + 1]) return parts[idx + 1];
  return parts[parts.length - 1] || "";
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function syncHeights() {
  if (window.CVH && typeof window.CVH.syncWatchHeights === "function") {
    window.CVH.syncWatchHeights();
  }
}

function showPollError(message) {
  if (window.CVH && typeof window.CVH.showWatchPollError === "function") {
    window.CVH.showWatchPollError(message);
  }
}

function sideToMoveFromFen(fen) {
  return String(fen || "").indexOf(" b ") >= 0 ? "Black to move" : "White to move";
}

function statusLabel(s) {
  if (s.status === "finished") {
    return s.result === "correct" ? "Solved" : "Failed";
  }
  if (s.status === "abandoned") return "Abandoned";
  return "In progress";
}

function stepParts(label) {
  const text = String(label || "");
  const mover = text.match(/^(\d+)\.\.\.\s*(.*)$/);
  if (mover) return { num: Number(mover[1]), san: mover[2], opponent: true };
  const moverb = text.match(/^(\d+)\.\s*(.*)$/);
  if (moverb) return { num: Number(moverb[1]), san: moverb[2], opponent: false };
  return { num: null, san: text, opponent: false };
}

function moveRowsFromPlies(plies) {
  const rows = [];
  for (let i = 0; i < plies.length; i++) {
    const part = stepParts(plies[i] && plies[i].label);
    const num = part.num != null ? part.num : Math.floor(i / 2) + 1;
    let row = rows.find((r) => r.num === num);
    if (!row) {
      row = { num: num, agent: "", opponent: "" };
      rows.push(row);
    }
    if (part.opponent) row.opponent = part.san;
    else row.agent = part.san;
  }
  return rows;
}

function moveRowsFromSan(submitted, opponent) {
  const rows = [];
  const count = Math.max(submitted.length, opponent.length);
  for (let i = 0; i < count; i++) {
    rows.push({
      num: i + 1,
      agent: submitted[i] || "",
      opponent: opponent[i] || "",
    });
  }
  return rows;
}

function renderMoveRows(rows, onStyle, onPly) {
  const mv = document.getElementById("mv");
  if (!mv) return;
  if (!rows.length) {
    mv.innerHTML = '<p style="color:var(--faint);margin:0">No moves yet.</p>';
    return;
  }
  const fromPlies = onStyle === "plies";
  mv.innerHTML = rows
    .map((row, i) => {
      const wOn = fromPlies && onPly != null && onPly >= i * 2;
      const bOn = fromPlies && onPly != null && onPly >= i * 2 + 1;
      const wCls = wOn ? " w on" : "";
      const bCls = bOn ? " b on" : "";
      const bClick = bOn || (onPly != null && onPly < i * 2 + 1) ? "" : " data-ply";
      return (
        '<div class="move-row"><span class="mn">' +
        escHtml(String(row.num)) +
        '.</span><span class="w' +
        wCls +
        '" data-ply="' +
        (i * 2) +
        '">' +
        escHtml(row.agent) +
        '</span><span class="b' +
        bCls +
        '"' +
        bClick +
        ' data-ply="' +
        (i * 2 + 1) +
        '">' +
        escHtml(row.opponent) +
        "</span></div>"
      );
    })
    .join("");
  mv.querySelectorAll("[data-ply]").forEach((cell) => {
    cell.addEventListener("click", () => {
      const ply = Number(cell.getAttribute("data-ply"));
      if (Number.isFinite(ply) && replay && replay.plies) goToStep(ply);
    });
  });
  const active = mv.querySelector(".on");
  if (active) active.scrollIntoView({ block: "nearest" });
}

async function main() {
  let ATTEMPT_ID = attemptIdFromPage();
  const mount = document.getElementById("board");
  if (!ATTEMPT_ID || !mount) return;

  const board = new Chessboard(mount, {
    position: undefined,
    assetsUrl: BOARD_ASSETS,
    orientation: COLOR.white,
    style: {
      borderType: BORDER_TYPE.none,
      showCoordinates: true,
      pieces: { file: "pieces/staunty.svg" },
      animationDuration: 150,
    },
  });

  let lastFen = null;
  let replay = null;
  let scanPly = -1;
  let pollTimer = null;
  let chainTimer = null;
  let followTimer = null;
  let agentKey = null;
  let agentName = null;
  let currentStartedAt = null;

  function setPosition(fen, animate) {
    const doAnimate = !!animate && lastFen != null && fen !== lastFen;
    lastFen = fen;
    return board.setPosition(fen, doAnimate);
  }

  function turnLabel(fen) {
    const el = document.getElementById("board-label-turn");
    if (el) el.textContent = sideToMoveFromFen(fen);
  }

  function renderMeta(state) {
    const dl = document.getElementById("meta");
    if (dl) {
      dl.innerHTML =
        "<dt>Attempt</dt><dd>" +
        escHtml(state.attempt_id) +
        "</dd><dt>Agent</dt><dd>" +
        escHtml(state.agent_name) +
        "</dd>";
    }
    const statusEl = document.getElementById("state-status");
    const resultEl = document.getElementById("state-result");
    const diffEl = document.getElementById("state-difficulty");
    if (statusEl) statusEl.textContent = statusLabel(state);
    if (resultEl) resultEl.textContent = state.result || "—";
    if (diffEl) {
      diffEl.textContent =
        state.puzzle_rating > 0 ? String(state.puzzle_rating) : "—";
    }
  }

  function renderFinishedMeta(r) {
    const puzzle = document.getElementById("state-puzzle");
    const puzzleLabel = document.getElementById("state-puzzle-label");
    if (puzzle && puzzleLabel) {
      puzzleLabel.hidden = false;
      puzzle.hidden = false;
      puzzle.textContent = r.puzzle_id || "—";
    }
    const source = document.getElementById("state-source");
    const sourceLabel = document.getElementById("state-source-label");
    if (source && sourceLabel) {
      sourceLabel.hidden = false;
      source.hidden = false;
      if (r.source_link) {
        source.innerHTML =
          '<a href="' +
          escHtml(r.source_link) +
          '" target="_blank" rel="noopener" style="color:var(--link)">View source game</a>';
      } else {
        source.textContent = "—";
      }
    }
    const rating = document.getElementById("state-rating");
    const ratingLabel = document.getElementById("state-rating-label");
    if (rating && ratingLabel) {
      ratingLabel.hidden = false;
      rating.hidden = false;
      let text = "—";
      if (r.rating_before != null && r.rating_after != null) {
        const delta =
          r.rating_change != null
            ? " (" + (Number(r.rating_change) > 0 ? "+" : "") + r.rating_change + ")"
            : "";
        text = r.rating_before + " → " + r.rating_after + delta;
      }
      rating.textContent = text;
    }
  }

  function renderAgentMetrics(state) {
    if (!window.CVH) return;
    const modelId = state.model_id || null;
    const perfEl = document.getElementById("state-agent-performance");
    const perfLbl = document.getElementById("state-performance-label");
    const rating = document.getElementById("state-agent-rating");
    const dev = document.getElementById("state-deviation");
    const attempts = document.getElementById("state-attempts");
    const solves = document.getElementById("state-solves");

    function applyPuzzleAgent(agent) {
      if (agent) {
        if (rating) rating.textContent =
          agent.rating != null ? String(agent.rating) : "—";
        if (dev) dev.textContent =
          agent.deviation != null ? String(agent.deviation) : "—";
        if (attempts) attempts.textContent =
          String(agent.attempts != null ? agent.attempts : "—");
        if (solves) solves.textContent =
          String(agent.solves != null ? agent.solves : "—");
      } else {
        if (rating) rating.textContent = "—";
        if (dev) dev.textContent = "—";
        if (attempts) attempts.textContent = "—";
        if (solves) solves.textContent = "—";
      }
    }

    function applyPerformance(agent) {
      if (!perfEl) return;
      const value = agent && agent.mean_play_rating != null
        ? String(Math.round(Number(agent.mean_play_rating)))
        : "—";
      perfEl.textContent = value;
      if (perfLbl) perfLbl.hidden = false;
      perfEl.hidden = false;
    }

    const puzzleReq = fetch("/api/leaderboard/puzzles/live")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const agents = (data && data.agents) || [];
        const agent = modelId
          ? agents.find((a) => a.id === modelId)
          : agents.find((a) => a.name === state.agent_name);
        applyPuzzleAgent(agent);
      })
      .catch(() => {
        applyPuzzleAgent(null);
      });

    const ladderReq = fetch("/api/leaderboard/live")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const agents = (data && data.agents) || [];
        const agent = modelId
          ? agents.find((a) => a.id === modelId)
          : agents.find((a) => a.name === state.agent_name);
        applyPerformance(agent);
      })
      .catch(() => {
        if (window.CVH_INLINE_SNAPSHOT && window.CVH_INLINE_SNAPSHOT.agents) {
          const agents = window.CVH_INLINE_SNAPSHOT.agents;
          const agent = modelId
            ? agents.find((a) => a.id === modelId)
            : agents.find((a) => a.name === state.agent_name);
          applyPerformance(agent);
        } else {
          applyPerformance(null);
        }
      });

    return Promise.all([puzzleReq, ladderReq]).catch(() => {});
  }

  function renderLiveMoves(state) {
    const heading = document.getElementById("moves-heading");
    if (heading) heading.textContent = "Moves";
    renderMoveRows(
      moveRowsFromSan(state.submitted_moves || [], state.opponent_moves || []),
      "none",
      null
    );
  }

  function renderSolution() {
    const heading = document.getElementById("moves-heading");
    if (heading) heading.textContent = "Solution";
    const mv = document.getElementById("mv");
    if (!mv || !replay) return;
    const rows = moveRowsFromPlies(replay.plies || []);
    renderMoveRows(rows, "plies", scanPly);
    if (replay.result === "failed" && replay.first_wrong_move) {
      const wrong = document.createElement("div");
      wrong.className = "move-row";
      wrong.innerHTML =
        '<span class="mn">✗</span><span class="w is-wrong" title="First wrong move (attempt ended)">' +
        escHtml(replay.first_wrong_move) +
        "</span><span class='b'></span>";
      mv.appendChild(wrong);
    }
  }

  function goToStep(index) {
    if (!replay || !replay.plies) return;
    const plies = replay.plies;
    const n = Math.max(-1, Math.min(index, plies.length - 1));
    scanPly = n;
    setPosition(n < 0 ? replay.start_fen : plies[n].fen, true);
    turnLabel(n < 0 ? replay.start_fen : plies[n].fen);
    renderSolution();
  }

  async function loadReplay() {
    try {
      const r = await fetch(
        "/api/v1/puzzles/public/" +
          encodeURIComponent(ATTEMPT_ID) +
          "/replay"
      );
      if (!r.ok) return;
      replay = await r.json();
      scanPly = replay.plies ? replay.plies.length - 1 : -1;
      if (scanPly >= 0 && replay.plies.length) {
        setPosition(replay.plies[scanPly].fen, true);
      }
      turnLabel(scanPly >= 0 ? replay.plies[scanPly].fen : replay.start_fen);
      renderSolution();
      renderFinishedMeta(replay);
    } catch (e) {
      /* ignore */
    }
  }

  function renderChain(rows) {
    const list = document.getElementById("chain");
    const empty = document.getElementById("chain-empty");
    if (!list || !empty) return;
    const visible = (rows || []).filter((row) => row.attempt_id !== ATTEMPT_ID);
    const all = (rows || []).slice();
    if (!all.length) {
      list.hidden = true;
      empty.hidden = false;
      return;
    }
    empty.hidden = true;
    list.hidden = false;
    list.innerHTML = all
      .map((row) => {
        const isYou = row.attempt_id === ATTEMPT_ID;
        const label =
          (row.started_at ? new Date(row.started_at).toLocaleTimeString() : "") +
          " · " +
          (isYou ? "this attempt" : statusLabel(row) + " · " + row.moves_played + " moves");
        if (isYou) {
          return '<li class="chain-you">' + escHtml(label) + "</li>";
        }
        return (
          '<li><a href="' +
          escHtml(row.watch_url || "/p/" + row.attempt_id) +
          '">' +
          escHtml(label) +
          "</a></li>"
        );
      })
      .join("");
    if (!visible.length) return;
  }

  async function refreshChain() {
    const keyParam = agentKey
      ? "by_key=" + encodeURIComponent(agentKey)
      : agentName
        ? "by_agent=" + encodeURIComponent(agentName)
        : null;
    if (!keyParam) return;
    try {
      const r = await fetch(
        "/api/v1/puzzles/public/attempts?" + keyParam + "&limit=50"
      );
      if (!r.ok) return;
      const rows = (await r.json()).attempts || [];
      renderChain(rows);
      if (!currentStartedAt) return;
      const newer = rows
        .filter(
          (row) =>
            row.attempt_id !== ATTEMPT_ID &&
            String(row.started_at || "") > String(currentStartedAt)
        )
        .sort((a, b) =>
          String(b.started_at).localeCompare(String(a.started_at))
        );
      if (newer.length && !followTimer) {
        const banner = document.getElementById("follow-banner");
        if (banner) {
          banner.textContent =
            "Agent started the next puzzle — following in " +
            Math.round(FOLLOW_DELAY_MS / 1000) +
            "s…";
          banner.style.display = "block";
        }
        followTimer = setTimeout(
          () => followTo(newer[0].attempt_id),
          FOLLOW_DELAY_MS
        );
      }
    } catch (e) {
      /* ignore */
    }
  }

  function startChainTracking(state) {
    agentKey = state.key || agentKey;
    agentName = state.agent_name || agentName;
    currentStartedAt = state.started_at || currentStartedAt;
    if ((!agentKey && !agentName) || chainTimer) return;
    chainTimer = setInterval(refreshChain, CHAIN_POLL_MS);
    refreshChain();
  }

  function resetWatch() {
    lastFen = null;
    replay = null;
    scanPly = -1;
    if (followTimer) {
      clearTimeout(followTimer);
      followTimer = null;
    }
    const banner = document.getElementById("follow-banner");
    if (banner) {
      banner.style.display = "none";
      banner.textContent = "";
    }
    renderMeta({ attempt_id: ATTEMPT_ID, agent_name: "—", status: "active", result: null });
    const puzzle = document.getElementById("state-puzzle");
    const puzzleLabel = document.getElementById("state-puzzle-label");
    const source = document.getElementById("state-source");
    const sourceLabel = document.getElementById("state-source-label");
    const rating = document.getElementById("state-rating");
    const ratingLabel = document.getElementById("state-rating-label");
    if (puzzle) puzzle.hidden = true;
    if (puzzleLabel) puzzleLabel.hidden = true;
    if (source) source.hidden = true;
    if (sourceLabel) sourceLabel.hidden = true;
    if (rating) rating.hidden = true;
    if (ratingLabel) ratingLabel.hidden = true;
    const heading = document.getElementById("moves-heading");
    if (heading) heading.textContent = "Moves";
    const mv = document.getElementById("mv");
    if (mv) mv.innerHTML = "";
  }

  function followTo(nextId) {
    followTimer = null;
    window.history.replaceState({}, "", "/p/" + encodeURIComponent(nextId));
    ATTEMPT_ID = nextId;
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    resetWatch();
    poll();
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function poll() {
    try {
      const r = await fetch(
        "/api/v1/puzzles/public/" + encodeURIComponent(ATTEMPT_ID)
      );
      if (!r.ok) return;
      const state = await r.json();
      renderMeta(state);
      renderAgentMetrics(state);
      renderLiveMoves(state);
      setPosition(state.fen, true);
      turnLabel(state.fen);
      if (state.status === "finished") {
        stopPolling();
        await loadReplay();
        startChainTracking(state);
      } else if (state.status === "abandoned") {
        stopPolling();
        startChainTracking(state);
      } else {
        startChainTracking(state);
      }
      syncHeights();
      showPollError("");
    } catch (e) {
      showPollError("Could not refresh puzzle state — is the server online?");
    }
  }

  window.addEventListener("resize", syncHeights);
  if (typeof ResizeObserver !== "undefined") {
    const wrap = document.getElementById("board-wrap");
    if (wrap) {
      const ro = new ResizeObserver(() => syncHeights());
      ro.observe(wrap);
    }
  }

  pollTimer = setInterval(poll, POLL_MS);
  poll();
}

main();