/**
 * Public puzzle watch/replay page (/p/{id}).
 * Mirrors the game spectator layout: info column, board column, moves column.
 * Live state polls the observer-safe API; after finish, Played vs Solution are
 * shown separately. Navigation to other attempts is via the chain links or URL only.
 */

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

const BOARD_ASSETS =
  "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/assets/";
const POLL_MS = 3000;
const CHAIN_POLL_MS = 15000;

function watchHrefForRow(row, prefix) {
  const url = row.watch_url;
  if (url) {
    const trimmed = String(url).replace(/\/+$/, "");
    const parts = trimmed.split("/").filter(Boolean);
    const last = parts[parts.length - 1] || "";
    if (last && last !== "p" && last !== "i" && last !== "index.html") {
      return url;
    }
  }
  if (row.attempt_id) return prefix + row.attempt_id;
  return "";
}

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
    if (decoded && decoded !== "index.html" && decoded !== "p") return decoded;
  }
  const parts = window.location.pathname.replace(/\/+$/, "").split("/");
  const idx = parts.indexOf("p");
  if (idx < 0) return "";
  let id = parts[idx + 1] || "";
  if (!id) return "";
  try {
    id = decodeURIComponent(id);
  } catch (_e) {
    /* keep raw segment */
  }
  id = id.trim();
  if (!id || id === "index.html" || id === "p") return "";
  return id;
}

function missingAttemptIdMessage() {
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path === "/p" || path === "/p/") {
    return (
      "No puzzle attempt id — the URL may have been stripped " +
      "(check the link includes the full attempt id after /p/)."
    );
  }
  return "No puzzle attempt id in this URL.";
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
      : "This puzzle attempt was not found.";
  }
  if (status === 502 || status === 503) {
    return "Game server is offline — try again when the operator is online.";
  }
  return "Could not load puzzle " + (kind || "data") + " (HTTP " + status + ").";
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

function solutionRowsFromReplay(replay) {
  const rows = moveRowsFromSan(
    replay.solution_agent_moves || [],
    replay.solution_opponent_moves || []
  );
  if (rows.length) return rows;
  const uci = replay.solution_moves || [];
  if (!uci.length) return rows;
  const agent = [];
  const opponent = [];
  for (let i = 0; i < uci.length; i++) {
    if (i % 2 === 0) agent.push(uci[i]);
    else opponent.push(uci[i]);
  }
  return moveRowsFromSan(agent, opponent);
}

function moveHeaderHtml() {
  return (
    '<div class="move-row move-header">' +
    '<span class="mn"></span><span class="w">Agent</span><span class="b">Reply</span>' +
    "</div>"
  );
}

function renderMoveRows(rows, options) {
  const opts = options || {};
  const mv = document.getElementById("mv");
  if (!mv) return;
  if (!rows.length) {
    mv.innerHTML = '<p style="color:var(--faint);margin:0">No moves yet.</p>';
    return;
  }
  const fromPlies = opts.style === "plies";
  const onPly = opts.onPly;
  const wrongSan = opts.wrongSan || "";
  const interactive = opts.interactive !== false;
  let html = opts.includeHeader === false ? "" : moveHeaderHtml();
  html += rows
    .map((row, i) => {
      const wOn = fromPlies && onPly != null && onPly >= i * 2;
      const bOn = fromPlies && onPly != null && onPly >= i * 2 + 1;
      const wWrong = wrongSan && row.agent === wrongSan;
      const wCls =
        (wOn ? " w on" : " w") + (wWrong ? " is-wrong" : "");
      const bCls = bOn ? " b on" : " b";
      const wAttrs = interactive
        ? ' data-ply="' + i * 2 + '"'
        : "";
      const bAttrs = interactive
        ? (bOn || (onPly != null && onPly < i * 2 + 1)
            ? ' data-ply="' + (i * 2 + 1) + '"'
            : ' data-ply="' + (i * 2 + 1) + '"')
        : "";
      return (
        '<div class="move-row"><span class="mn">' +
        escHtml(String(row.num)) +
        '.</span><span class="' +
        wCls.trim() +
        '"' +
        wAttrs +
        (wWrong ? ' title="First wrong move (attempt ended)"' : "") +
        ">" +
        escHtml(row.agent) +
        '</span><span class="' +
        bCls.trim() +
        '"' +
        bAttrs +
        ">" +
        escHtml(row.opponent) +
        "</span></div>"
      );
    })
    .join("");
  mv.innerHTML = html;
  if (interactive) {
    mv.querySelectorAll("[data-ply]").forEach((cell) => {
      cell.addEventListener("click", () => {
        const ply = Number(cell.getAttribute("data-ply"));
        if (Number.isFinite(ply) && replay && replay.plies) goToStep(ply);
      });
    });
    const active = mv.querySelector(".on");
    if (active) active.scrollIntoView({ block: "nearest" });
  }
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

  let lastFen = null;
  let replay = null;
  let scanPly = -1;
  let pollTimer = null;
  let chainTimer = null;
  let agentKey = null;
  let agentName = null;
  let finished = false;

  function setPosition(fen, animate) {
    annotations.clearAnnotations();
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
    const outcomeEl = document.getElementById("state-outcome");
    const diffEl = document.getElementById("state-difficulty");
    if (outcomeEl) outcomeEl.textContent = statusLabel(state);
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
    const ratingVal = document.getElementById("state-agent-rating-value");
    const devSub = document.getElementById("state-deviation-sub");
    const attempts = document.getElementById("state-attempts");
    const solves = document.getElementById("state-solves");

    function applyPuzzleAgent(agent) {
      if (agent && agent.rating != null) {
        if (ratingVal) {
          ratingVal.textContent = String(agent.rating);
        }
        if (devSub) {
          if (agent.deviation != null) {
            devSub.textContent = " ±" + agent.deviation;
            devSub.title = "Glicko deviation (RD)";
          } else {
            devSub.textContent = "";
            devSub.title = "";
          }
        }
        if (attempts) {
          attempts.textContent = String(
            agent.attempts != null ? agent.attempts : "—"
          );
        }
        if (solves) {
          solves.textContent = String(agent.solves != null ? agent.solves : "—");
        }
      } else {
        if (ratingVal) ratingVal.textContent = "—";
        if (devSub) {
          devSub.textContent = "";
          devSub.title = "";
        }
        if (attempts) attempts.textContent = "—";
        if (solves) solves.textContent = "—";
      }
    }

    if (state.agent_summary) {
      applyPuzzleAgent(state.agent_summary);
      return;
    }

    const modelId = state.model_id || null;
    const fetchCached =
      window.CVH && typeof window.CVH.fetchSpecialtyLeaderboard === "function"
        ? window.CVH.fetchSpecialtyLeaderboard("puzzles")
        : fetch("/api/leaderboard/puzzles/live").then((res) =>
            res.ok ? res.json() : null
          );
    fetchCached
      .then((data) => {
        const agents = (data && data.agents) || [];
        const agent = modelId
          ? agents.find((a) => a.id === modelId)
          : agents.find((a) => a.name === state.agent_name);
        applyPuzzleAgent(agent);
      })
      .catch(() => applyPuzzleAgent(null));
  }

  function renderLiveMoves(state) {
    const heading = document.getElementById("moves-heading");
    if (heading) heading.textContent = "Moves";
    const mv = document.getElementById("mv");
    if (!mv) return;
    const rows = moveRowsFromSan(
      state.submitted_moves || [],
      state.opponent_moves || []
    );
    if (!rows.length) {
      mv.innerHTML = '<p style="color:var(--faint);margin:0">No moves yet.</p>';
      return;
    }
    renderMoveRows(rows, { interactive: false });
  }

  function renderFinishedMoves() {
    const heading = document.getElementById("moves-heading");
    if (heading) heading.textContent = "Moves";
    const mv = document.getElementById("mv");
    if (!mv || !replay) return;

    let playedRows = moveRowsFromPlies(replay.plies || []);
    if (!playedRows.length && replay.first_wrong_move) {
      playedRows = [{ num: 1, agent: replay.first_wrong_move, opponent: "" }];
    }
    const solutionRows = solutionRowsFromReplay(replay);

    let wrongSan = "";
    if (replay.result === "failed") {
      if (playedRows.length) {
        const lastRow = playedRows[playedRows.length - 1];
        if (lastRow.agent) wrongSan = lastRow.agent;
      } else if (replay.first_wrong_move) {
        wrongSan = replay.first_wrong_move;
      }
    }

    let html = '<h3 class="moves-subhead">Played</h3>';
    if (!playedRows.length) {
      html += '<p style="color:var(--faint);margin:0">No moves played.</p>';
    } else {
      html += moveHeaderHtml();
      html += playedRows
        .map((row, i) => {
          const wOn = scanPly != null && scanPly >= i * 2;
          const bOn = scanPly != null && scanPly >= i * 2 + 1;
          const wWrong = wrongSan && row.agent === wrongSan;
          const wCls =
            (wOn ? " w on" : " w") + (wWrong ? " is-wrong" : "");
          const bCls = bOn ? " b on" : " b";
          return (
            '<div class="move-row"><span class="mn">' +
            escHtml(String(row.num)) +
            '.</span><span class="' +
            wCls.trim() +
            '" data-ply="' +
            i * 2 +
            '"' +
            (wWrong ? ' title="First wrong move (attempt ended)"' : "") +
            ">" +
            escHtml(row.agent) +
            '</span><span class="' +
            bCls.trim() +
            '" data-ply="' +
            (i * 2 + 1) +
            '">' +
            escHtml(row.opponent) +
            "</span></div>"
          );
        })
        .join("");
    }

    html += '<h3 class="moves-subhead">Solution</h3>';
    if (!solutionRows.length) {
      html += '<p style="color:var(--faint);margin:0">Solution not available.</p>';
    } else {
      html += moveHeaderHtml();
      html += solutionRows
        .map((row) => {
          return (
            '<div class="move-row move-static"><span class="mn">' +
            escHtml(String(row.num)) +
            '.</span><span class="w">' +
            escHtml(row.agent) +
            '</span><span class="b">' +
            escHtml(row.opponent) +
            "</span></div>"
          );
        })
        .join("");
    }

    mv.innerHTML = html;
    mv.querySelectorAll("[data-ply]").forEach((cell) => {
      cell.addEventListener("click", () => {
        const ply = Number(cell.getAttribute("data-ply"));
        if (Number.isFinite(ply) && replay && replay.plies) goToStep(ply);
      });
    });
    const active = mv.querySelector(".on");
    if (active) active.scrollIntoView({ block: "nearest" });
  }

  function goToStep(index) {
    if (!replay || !replay.plies) return;
    const plies = replay.plies;
    const n = Math.max(-1, Math.min(index, plies.length - 1));
    scanPly = n;
    setPosition(n < 0 ? replay.start_fen : plies[n].fen, true);
    turnLabel(n < 0 ? replay.start_fen : plies[n].fen);
    renderFinishedMoves();
  }

  async function loadReplay() {
    try {
      const r = await fetch(
        "/api/v1/puzzles/public/" +
          encodeURIComponent(ATTEMPT_ID) +
          "/replay"
      );
      if (!r.ok) {
        showPollError(httpErrorMessage(r.status, "replay"));
        return;
      }
      replay = await r.json();
      scanPly = replay.plies ? replay.plies.length - 1 : -1;
      if (scanPly >= 0 && replay.plies.length) {
        setPosition(replay.plies[scanPly].fen, true);
      }
      turnLabel(scanPly >= 0 ? replay.plies[scanPly].fen : replay.start_fen);
      renderFinishedMoves();
      renderFinishedMeta(replay);
      showPollError("");
    } catch (e) {
      showPollError("Could not load puzzle replay — is the server online?");
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
          (isYou ? "this attempt" : statusLabel(row) + " · " + row.moves_played + " moves");
        if (isYou) {
          return '<li class="chain-you">' + escHtml(label) + "</li>";
        }
        const href = watchHrefForRow(row, "/p/");
        if (!href) {
          return "<li>" + escHtml(label) + "</li>";
        }
        return (
          '<li><a href="' +
          escHtml(href) +
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
        "/api/v1/puzzles/public/attempts?" + keyParam + "&limit=50"
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
        "/api/v1/puzzles/public/" + encodeURIComponent(ATTEMPT_ID)
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
      if (!finished) {
        renderLiveMoves(state);
      }
      setPosition(state.fen, true);
      turnLabel(state.fen);
      if (state.status === "finished") {
        finished = true;
        stopPolling();
        await loadReplay();
        startChainTracking(state);
      } else if (state.status === "abandoned") {
        finished = true;
        stopPolling();
        renderLiveMoves(state);
        const mvAbandoned = document.getElementById("mv");
        if (mvAbandoned) {
          mvAbandoned.insertAdjacentHTML(
            "beforeend",
            '<p style="color:var(--faint);margin:.75rem 0 0;font-size:.9em">' +
              "Replay (full Played and Solution) unlocks only when an attempt finishes normally." +
              "</p>"
          );
        }
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
