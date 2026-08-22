/**
 * Public board-identification watch/replay page (/i/{id}).
 * Mirrors the game spectator layout: info column, board column, review column.
 * Navigation to other attempts is via the attempt chain panel or URL.
 */

import { createWatchChain } from "./watch-chain.js?v=1";
import {
  Chessboard,
  COLOR,
  BORDER_TYPE,
} from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/Chessboard.js";
import {
  Markers,
} from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/extensions/markers/Markers.js";
import { Arrows } from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/extensions/arrows/Arrows.js";
import { createBoardAnnotations } from "./board-annotations.js";
import { bindLiveHealthGate } from "./live-health-gate.js";
import { createLivePollLoop } from "./live-poll-loop.js";

const IDENTIFY_EXACT_MARKER = {
  class: "identify-marker-exact",
  slice: "markerSquare",
};

const IDENTIFY_MISMATCH_MARKER = {
  class: "identify-marker-mismatch",
  slice: "markerSquare",
};

const BOARD_ASSETS =
  "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/assets/";
const POLL_MS = 3000;

function attemptIdFromPage() {
  const root = document.body;
  const fromData = root && root.dataset ? root.dataset.attemptId : "";
  if (fromData) {
    let decoded = fromData;
    try {
      decoded = decodeURIComponent(fromData);
    } catch (_e) {
      /* keep raw */
    }
    decoded = decoded.trim();
    if (decoded && decoded !== "index.html" && decoded !== "i") return decoded;
  }
  const parts = window.location.pathname.replace(/\/+$/, "").split("/");
  const idx = parts.indexOf("i");
  if (idx < 0) return "";
  let id = parts[idx + 1] || "";
  if (!id) return "";
  try {
    id = decodeURIComponent(id);
  } catch (_e) {
    /* keep raw segment */
  }
  id = id.trim();
  if (!id || id === "index.html" || id === "i") return "";
  return id;
}

function missingAttemptIdMessage() {
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path === "/i" || path === "/i/") {
    return (
      "No identification attempt id — the URL may have been stripped " +
      "(check the link includes the full attempt id after /i/)."
    );
  }
  return "No identification attempt id in this URL.";
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
  if (s.status === "active" && s.agent_joined === false) {
    return "Waiting for agent…";
  }
  if (s.status === "finished") {
    return s.result === "correct" ? "Identified" : "Mismatched";
  }
  if (s.status === "abandoned") return "Abandoned";
  return "In progress";
}

function updateAgentWaitChip(state) {
  const wrap = document.getElementById("board-wrap");
  if (!wrap) return;
  let chip = wrap.querySelector(".watch-agent-wait-chip");
  const waiting = state.status === "active" && state.agent_joined === false;
  if (!waiting) {
    if (chip) chip.remove();
    return;
  }
  if (!chip) {
    chip = document.createElement("span");
    chip.className = "watch-agent-wait-chip";
    chip.setAttribute("aria-live", "polite");
    chip.textContent = "Waiting for agent…";
    wrap.appendChild(chip);
  }
}

function fmtAccuracy(a) {
  if (a == null) return "—";
  return Math.round(Number(a) * 100) + "%";
}

function fmtYesNo(v) {
  if (v == null) return "—";
  return v ? "Yes" : "No";
}

function orientationFromSide(side) {
  return side === "black" ? COLOR.black : COLOR.white;
}

function sideToMoveFromSource(source) {
  if (!source) return null;
  if (source.side_to_move === "white" || source.side_to_move === "black") {
    return source.side_to_move;
  }
  if (!source.fen) return null;
  return String(source.fen).indexOf(" b ") >= 0 ? "black" : "white";
}

async function main() {
  const ATTEMPT_ID = attemptIdFromPage();
  const mount = document.getElementById("board");

  if (!ATTEMPT_ID) {
    showPollError(missingAttemptIdMessage());
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
    extensions: [
      {
        class: Markers,
        props: { autoMarkers: null },
      },
      { class: Arrows },
    ],
  });

  const annotations = createBoardAnnotations(board);

  let lastPolledFen = null;
  let lastPolledStatus = null;
  let lastPolledSubmitted = -1;
  let replay = null;
  let pollLoop = null;
  let finished = false;
  let boardOrientation = COLOR.white;

  function syncBoardOrientation(source) {
    const side = sideToMoveFromSource(source);
    if (!side) return;
    const orient = orientationFromSide(side);
    if (orient !== boardOrientation) {
      board.setOrientation(orient);
      boardOrientation = orient;
    }
  }

  function setPosition(fen, animate) {
    annotations.clearAnnotations();
    const doAnimate = !!animate && lastFen != null && fen !== lastFen;
    lastFen = fen;
    return board.setPosition(fen, doAnimate);
  }

  function renderMeta(state) {
    const dl = document.getElementById("meta");
    if (dl) {
      dl.innerHTML = "<dt>Agent</dt><dd>" + escHtml(state.agent_name) + "</dd>";
    }
    const outcomeEl = document.getElementById("state-outcome");
    const accEl = document.getElementById("state-accuracy");
    const fullEl = document.getElementById("state-full-position");
    const diffEl = document.getElementById("state-difficulty");
    const subEl = document.getElementById("state-submitted");
    if (outcomeEl) outcomeEl.textContent = statusLabel(state);
    updateAgentWaitChip(state);
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

  function rowsFromCorrectPieces(correct, submitted) {
    const map = submitted || {};
    const squares = {};
    Object.keys(correct || {}).forEach((sq) => (squares[sq] = true));
    Object.keys(map).forEach((sq) => (squares[sq] = true));
    return Object.keys(squares)
      .sort()
      .map((sq) => {
        const expected = (correct || {})[sq] || null;
        const got = map[sq] || null;
        let status = "exact";
        if (!expected) status = "extra";
        else if (!got) status = "missing";
        else if (expected === got) status = "exact";
        else if (expected[0] === got[0]) status = "wrong_type";
        else status = "wrong_color";
        return {
          square: sq,
          expected: expected,
          submitted: got,
          status: status,
        };
      });
  }

  function replyRows(replay) {
    const per = replay.per_square || [];
    if (per.length) return per;
    return rowsFromCorrectPieces(
      replay.correct_pieces || {},
      replay.submitted_pieces || {}
    );
  }

  function renderPlacementTable(rows, options) {
    const opts = options || {};
    const mv = document.getElementById("mv");
    if (!mv) return;
    if (!rows.length) {
      mv.innerHTML =
        '<p style="color:var(--faint);margin:0">No placement data.</p>';
      return;
    }
    const showSubmitted = opts.showSubmitted !== false;
    mv.innerHTML =
      '<table class="results-table"><thead><tr><th>Square</th><th>Expected</th>' +
      (showSubmitted ? "<th>Submitted</th><th>Status</th>" : "") +
      "</tr></thead><tbody>" +
      rows
        .map((r) => {
          let row =
            "<tr><td>" +
            escHtml(r.square) +
            "</td><td>" +
            escHtml(r.expected || "—") +
            "</td>";
          if (showSubmitted) {
            row +=
              "<td>" +
              escHtml(r.submitted || "—") +
              '</td><td><span class="badge ' +
              r.status +
              '">' +
              escHtml(String(r.status).replace("_", " ")) +
              "</span></td>";
          }
          return row + "</tr>";
        })
        .join("") +
      "</tbody></table>";
    if (opts.paintMarkers) paintReviewMarkers(rows);
    syncHeights();
  }

  function renderLiveCorrectPlacement(state) {
    const rows = rowsFromCorrectPieces(state.correct_pieces || {}, null);
    renderPlacementTable(rows, { showSubmitted: false, paintMarkers: true });
  }

  function paintReviewMarkers(rows) {
    board.removeMarkers(IDENTIFY_EXACT_MARKER);
    board.removeMarkers(IDENTIFY_MISMATCH_MARKER);
    rows.forEach((r) => {
      const marker =
        r.status === "exact" ? IDENTIFY_EXACT_MARKER : IDENTIFY_MISMATCH_MARKER;
      board.addMarker(marker, r.square);
    });
  }

  function renderReplay() {
    if (!replay) return;
    const rows = replyRows(replay);
    renderPlacementTable(rows, { showSubmitted: true, paintMarkers: true });
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

  function chainRowLabel(row, isCurrent) {
    const time = row.started_at
      ? new Date(row.started_at).toLocaleTimeString()
      : "";
    if (isCurrent) {
      return time ? time + " · this attempt" : "this attempt";
    }
    const acc =
      row.status === "finished" ? fmtAccuracy(row.accuracy) : "…";
    return (time ? time + " · " : "") + statusLabel(row) + " · " + acc;
  }

  const chain = createWatchChain({
    attemptId: ATTEMPT_ID,
    attemptsPath: "/api/v1/identify/public/attempts",
    watchPrefix: "/i/",
    chainKind: "identify",
    rowLabel: chainRowLabel,
    getFinished: () => finished,
  });

  function liveStateChanged(state) {
    return (
      state.fen !== lastPolledFen ||
      state.status !== lastPolledStatus ||
      state.submitted_count !== lastPolledSubmitted
    );
  }

  function rememberPolledState(state) {
    lastPolledFen = state.fen;
    lastPolledStatus = state.status;
    lastPolledSubmitted = state.submitted_count;
  }

  function stopPolling() {
    if (pollLoop) pollLoop.stop();
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
      syncBoardOrientation(state);
      renderMeta(state);
      renderAgentMetrics(state);
      const stateChanged = liveStateChanged(state);
      if (state.fen !== lastFen) {
        setPosition(state.fen, true);
      }
      if (state.status === "finished") {
        finished = true;
        stopPolling();
        await loadReplay();
        chain.startTracking(state);
      } else if (state.status === "abandoned") {
        finished = true;
        stopPolling();
        if (stateChanged) {
          renderLiveCorrectPlacement(state);
          rememberPolledState(state);
        }
        chain.startTracking(state);
      } else {
        if (stateChanged) {
          renderLiveCorrectPlacement(state);
          rememberPolledState(state);
        }
        chain.startTracking(state);
      }
      syncHeights();
      showPollError("");
    } catch (e) {
      showPollError("Could not refresh identification state — is the server online?");
    }
  }

  const copyIdBtn = document.getElementById("copy-attempt-id");
  const copyHintEl = document.getElementById("copy-hint");
  function showCopyHint(msg) {
    if (copyHintEl) {
      copyHintEl.textContent = msg;
      setTimeout(() => {
        if (copyHintEl && copyHintEl.textContent === msg) copyHintEl.textContent = "";
      }, 2000);
    }
  }
  if (copyIdBtn) {
    copyIdBtn.onclick = () => {
      if (!ATTEMPT_ID) return showCopyHint("No attempt ID");
      navigator.clipboard
        .writeText(ATTEMPT_ID)
        .then(() => showCopyHint("ID copied"));
    };
  }

  function startPolling() {
    if (finished) return;
    if (!pollLoop) {
      pollLoop = createLivePollLoop({ intervalMs: POLL_MS, poll });
    }
    pollLoop.start();
  }

  bindLiveHealthGate({
    onOnline: () => startPolling(),
    onOffline: () => {
      stopPolling();
      showPollError(
        "Game server is offline — try again when the operator is online."
      );
    },
  });

  window.addEventListener("resize", syncHeights);
  if (typeof ResizeObserver !== "undefined") {
    const wrap = document.getElementById("board-wrap");
    if (wrap) {
      const ro = new ResizeObserver(() => syncHeights());
      ro.observe(wrap);
    }
  }
}

main();
