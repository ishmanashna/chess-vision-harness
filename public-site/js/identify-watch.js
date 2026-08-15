/**
 * Public board-identification watch/replay page (/i/{id}).
 * Mirrors the game spectator layout: info column, board column, review column.
 * Navigation to other attempts is via the chain links or URL only.
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

function attemptIdFromPage() {
  const root = document.body;
  const fromData = root && root.dataset ? root.dataset.attemptId : "";
  if (fromData) return fromData;
  const parts = window.location.pathname.replace(/\/+$/, "").split("/");
  const idx = parts.indexOf("i");
  const id = idx >= 0 ? parts[idx + 1] : "";
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

function httpErrorMessage(status, kind) {
  if (status === 404) {
    return kind === "replay"
      ? "Replay is not available for this attempt."
      : "This identification attempt was not found.";
  }
  if (status === 502 || status === 503) {
    return "Game server is offline — try again when the operator is online.";
  }
  return "Could not load identification " + (kind || "data") + " (HTTP " + status + ").";
}

function statusLabel(s) {
  if (s.status === "finished") {
    return s.result === "correct" ? "Identified" : "Mismatched";
  }
  if (s.status === "abandoned") return "Abandoned";
  return "In progress";
}

function fmtAccuracy(a) {
  if (a == null) return "—";
  return Math.round(Number(a) * 100) + "%";
}

function fmtYesNo(v) {
  if (v == null) return "—";
  return v ? "Yes" : "No";
}

async function main() {
  const ATTEMPT_ID = attemptIdFromPage();
  const mount = document.getElementById("board");

  if (!ATTEMPT_ID) {
    showPollError("No identification attempt id in this URL.");
    const outcomeEl = document.getElementById("state-outcome");
    if (outcomeEl) outcomeEl.textContent = "—";
    return;
  }
  if (!mount) {
    showPollError("Board could not be initialized.");
    return;
  }

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
  let pollTimer = null;
  let chainTimer = null;
  let agentKey = null;
  let agentName = null;

  function setPosition(fen, animate) {
    const doAnimate = !!animate && lastFen != null && fen !== lastFen;
    lastFen = fen;
    return board.setPosition(fen, doAnimate);
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
    const outcomeEl = document.getElementById("state-outcome");
    const accEl = document.getElementById("state-accuracy");
    const fullEl = document.getElementById("state-full-position");
    const diffEl = document.getElementById("state-difficulty");
    const subEl = document.getElementById("state-submitted");
    if (outcomeEl) outcomeEl.textContent = statusLabel(state);
    if (accEl) accEl.textContent = fmtAccuracy(state.accuracy);
    if (fullEl) fullEl.textContent = fmtYesNo(state.full_position);
    if (diffEl) {
      diffEl.textContent = state.difficulty != null ? String(state.difficulty) : "—";
    }
    if (subEl) subEl.textContent = String(state.submitted_count);
  }

  function renderAgentMetrics(state) {
    const rate = document.getElementById("state-agent-rate");
    const full = document.getElementById("state-agent-full");
    const attempts = document.getElementById("state-attempts");

    function applyIdentifyAgent(agent) {
      if (agent) {
        if (rate) rate.textContent = fmtAccuracy(agent.mean_accuracy);
        if (full) full.textContent = fmtAccuracy(agent.full_position_rate);
        if (attempts) {
          attempts.textContent = String(
            agent.attempts != null ? agent.attempts : "—"
          );
        }
      } else {
        if (rate) rate.textContent = "—";
        if (full) full.textContent = "—";
        if (attempts) attempts.textContent = "—";
      }
    }

    if (state.agent_summary) {
      applyIdentifyAgent(state.agent_summary);
      return;
    }

    const modelId = state.model_id || null;
    const fetchCached =
      window.CVH && typeof window.CVH.fetchSpecialtyLeaderboard === "function"
        ? window.CVH.fetchSpecialtyLeaderboard("identify")
        : fetch("/api/leaderboard/identify/live").then((res) =>
            res.ok ? res.json() : null
          );
    fetchCached
      .then((data) => {
        const agents = (data && data.agents) || [];
        const agent = modelId
          ? agents.find((a) => a.id === modelId)
          : agents.find((a) => a.name === state.agent_name);
        applyIdentifyAgent(agent);
      })
      .catch(() => applyIdentifyAgent(null));
  }

  function replyRows(replay) {
    const per = replay.per_square || [];
    if (per.length) return per;
    const map = replay.submitted_pieces || {};
    const correct = replay.correct_pieces || {};
    const squares = {};
    Object.keys(map).forEach((sq) => (squares[sq] = true));
    Object.keys(correct).forEach((sq) => (squares[sq] = true));
    return Object.keys(squares)
      .sort()
      .map((sq) => ({
        square: sq,
        expected: correct[sq] || null,
        submitted: map[sq] || null,
        status:
          !correct[sq]
            ? "extra"
            : !map[sq]
              ? "missing"
              : correct[sq] === map[sq]
                ? "exact"
                : correct[sq][0] === map[sq][0]
                  ? "wrong_type"
                  : "wrong_color",
      }));
  }

  function renderReplay() {
    const mv = document.getElementById("mv");
    if (!mv || !replay) return;
    const rows = replyRows(replay);
    mv.innerHTML =
      '<table class="results-table"><thead><tr><th>Square</th><th>Expected</th>' +
      "<th>Submitted</th><th>Status</th></tr></thead><tbody>" +
      rows
        .map(
          (r) =>
            "<tr><td>" +
            escHtml(r.square) +
            "</td><td>" +
            escHtml(r.expected || "—") +
            "</td><td>" +
            escHtml(r.submitted || "—") +
            '</td><td><span class="badge ' +
            r.status +
            '">' +
            escHtml(String(r.status).replace("_", " ")) +
            "</span></td></tr>"
        )
        .join("") +
      "</tbody></table>";
    const wrap = document.getElementById("answer-wrap");
    if (wrap) {
      wrap.style.display = "block";
      wrap.classList.add("is-review");
      const img = document.getElementById("answer-img");
      if (img) {
        img.src = "/i/" + encodeURIComponent(ATTEMPT_ID) + "/answer.png?" + Date.now();
      }
    }
  }

  async function loadReplay() {
    try {
      const r = await fetch(
        "/api/v1/identify/public/" + encodeURIComponent(ATTEMPT_ID) + "/replay"
      );
      if (!r.ok) {
        showPollError(httpErrorMessage(r.status, "replay"));
        return;
      }
      replay = await r.json();
      renderReplay();
      showPollError("");
    } catch (e) {
      showPollError("Could not load identification replay — is the server online?");
    }
  }

  function renderChain(rows, opts) {
    const list = document.getElementById("chain");
    const empty = document.getElementById("chain-empty");
    if (!list || !empty) return;
    if (opts && opts.error) {
      list.hidden = true;
      empty.hidden = false;
      empty.textContent = opts.error;
      return;
    }
    const all = (rows || []).slice();
    if (!all.length) {
      list.hidden = true;
      empty.hidden = false;
      empty.textContent = "No attempts in this chain yet.";
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
          (isYou
            ? "this attempt"
            : statusLabel(row) +
              " · " +
              (row.status === "finished" ? fmtAccuracy(row.accuracy) : "…"));
        if (isYou) {
          return '<li class="chain-you">' + escHtml(label) + "</li>";
        }
        return (
          '<li><a href="' +
          escHtml(row.watch_url || "/i/" + row.attempt_id) +
          '">' +
          escHtml(label) +
          "</a></li>"
        );
      })
      .join("");
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
        "/api/v1/identify/public/attempts?" + keyParam + "&limit=50"
      );
      if (!r.ok) {
        const msg =
          r.status === 502 || r.status === 503
            ? "Could not load attempt chain — is the server online?"
            : "Could not load attempt chain.";
        renderChain([], { error: msg });
        return;
      }
      const rows = (await r.json()).attempts || [];
      renderChain(rows);
    } catch (e) {
      renderChain([], {
        error: "Could not load attempt chain — is the server online?",
      });
    }
  }

  function startChainTracking(state) {
    agentKey = state.key || agentKey;
    agentName = state.agent_name || agentName;
    if ((!agentKey && !agentName) || chainTimer) return;
    chainTimer = setInterval(refreshChain, CHAIN_POLL_MS);
    refreshChain();
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
        "/api/v1/identify/public/" + encodeURIComponent(ATTEMPT_ID)
      );
      if (!r.ok) {
        showPollError(httpErrorMessage(r.status, "state"));
        const outcomeEl = document.getElementById("state-outcome");
        if (outcomeEl && outcomeEl.textContent === "Loading…") {
          outcomeEl.textContent = "—";
        }
        if (r.status === 404) stopPolling();
        return;
      }
      const state = await r.json();
      renderMeta(state);
      renderAgentMetrics(state);
      setPosition(state.fen, true);
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
      showPollError("Could not refresh identification state — is the server online?");
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
