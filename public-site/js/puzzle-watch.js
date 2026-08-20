/**
 * Public puzzle watch/replay page (/p/{id}).
 * Mirrors the game spectator layout: info column, board column, moves column.
 * Live state polls the observer-safe API; after finish, Played vs Solution are
 * shown separately. Navigation to other attempts is via the attempt chain panel or URL.
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
import {
  createBoardAnnotations,
  knightCornerSquare,
} from "./board-annotations.js";
import {
  lastUciBetweenFens,
  paintLastMoveMarkers,
  squaresFromUci,
} from "./board-last-move.js";
import { pinScrollToBottom } from "./moves-scroll.js";

const BOARD_ASSETS =
  "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/assets/";
const POLL_MS = 3000;

/** Finish-overlay arrows: annotation shaft/head geometry, red/green only. */
const WRONG_ARROW_TYPE = {
  class: "arrow-default arrow-result-wrong",
  slice: "arrowDefault",
};
const WRONG_ARROW_SHAFT_TYPE = {
  class: "arrow-annotation-shaft arrow-result-wrong",
  slice: "arrowDefault",
  headSize: 0,
};
const SOLUTION_ARROW_TYPE = {
  class: "arrow-default arrow-result-solution",
  slice: "arrowDefault",
};
const SOLUTION_ARROW_SHAFT_TYPE = {
  class: "arrow-annotation-shaft arrow-result-solution",
  slice: "arrowDefault",
  headSize: 0,
};

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

function isValidSquare(sq) {
  if (!sq || sq.length !== 2) return false;
  const f = sq.charCodeAt(0);
  const r = sq.charCodeAt(1);
  return f >= 97 && f <= 104 && r >= 49 && r <= 56;
}

function parseUciSquares(uci) {
  const sq = squaresFromUci(uci);
  if (!sq) return null;
  if (!isValidSquare(sq.from) || !isValidSquare(sq.to)) return null;
  return sq;
}

function turnLabelFromSide(side) {
  return side === "black" ? "Black to move" : "White to move";
}

function orientationFromSide(side) {
  return side === "black" ? COLOR.black : COLOR.white;
}

function sideToMoveFromSource(source) {
  if (!source) return null;
  if (source.side_to_move === "white" || source.side_to_move === "black") {
    return source.side_to_move;
  }
  const fen = source.fen || source.start_fen;
  if (!fen) return null;
  return String(fen).indexOf(" b ") >= 0 ? "black" : "white";
}

function statusLabel(s) {
  if (s.status === "active" && s.agent_joined === false) {
    return "Waiting for agent…";
  }
  if (s.status === "finished") {
    if (s.result === "correct") return "Solved";
    if (s.failure_reason === "illegal_move") return "Illegal move";
    if (s.failure_reason === "wrong_move") return "Wrong move";
    return "Failed";
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

function solutionRowsFromState(state) {
  const rows = moveRowsFromSan(
    state.solution_agent_moves || [],
    state.solution_opponent_moves || []
  );
  if (rows.length) return rows;
  const uci = state.solution_moves || [];
  if (!uci.length) return rows;
  const agent = [];
  const opponent = [];
  for (let i = 0; i < uci.length; i++) {
    if (i % 2 === 0) agent.push(uci[i]);
    else opponent.push(uci[i]);
  }
  return moveRowsFromSan(agent, opponent);
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
  }
  if (opts.liveFollow) {
    pinScrollToBottom(mv);
  } else if (interactive) {
    const active = mv.querySelector(".on");
    if (active) active.scrollIntoView({ block: "center" });
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
  let finished = false;
  let puzzleSideToMove = null;
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

  function cachePuzzleSide(source) {
    if (!source) return;
    if (source.side_to_move === "white" || source.side_to_move === "black") {
      puzzleSideToMove = source.side_to_move;
      return;
    }
    if (source.start_fen) {
      puzzleSideToMove =
        String(source.start_fen).indexOf(" b ") >= 0 ? "black" : "white";
      return;
    }
    if (!puzzleSideToMove && source.fen) {
      puzzleSideToMove =
        String(source.fen).indexOf(" b ") >= 0 ? "black" : "white";
    }
  }

  function clearResultArrows() {
    board.removeArrows(WRONG_ARROW_TYPE);
    board.removeArrows(WRONG_ARROW_SHAFT_TYPE);
    board.removeArrows(SOLUTION_ARROW_TYPE);
    board.removeArrows(SOLUTION_ARROW_SHAFT_TYPE);
  }

  function addResultArrow(arrowType, shaftType, from, to) {
    const corner = knightCornerSquare(from, to);
    if (corner) {
      board.addArrow(shaftType, from, corner);
      board.addArrow(arrowType, corner, to);
      return;
    }
    board.addArrow(arrowType, from, to);
  }

  function wrongUciForReplay(r) {
    if (!r) return null;
    const submitted = r.submitted_moves || [];
    if (!submitted.length) return null;
    return submitted[submitted.length - 1];
  }

  function solutionUciForFailPly(r) {
    if (!r) return null;
    const submitted = r.submitted_moves || [];
    if (!submitted.length) return null;
    return (r.solution_moves || [])[2 * (submitted.length - 1)] || null;
  }

  function paintResultArrows(r) {
    clearResultArrows();
    if (!r || r.result !== "failed") return;
    const solSq = parseUciSquares(solutionUciForFailPly(r));
    if (solSq) {
      addResultArrow(
        SOLUTION_ARROW_TYPE,
        SOLUTION_ARROW_SHAFT_TYPE,
        solSq.from,
        solSq.to
      );
    }
    const wrongSq = parseUciSquares(wrongUciForReplay(r));
    if (wrongSq) {
      addResultArrow(
        WRONG_ARROW_TYPE,
        WRONG_ARROW_SHAFT_TYPE,
        wrongSq.from,
        wrongSq.to
      );
    }
  }

  function playedMoveClass(r, rowIndex, field) {
    if (!r || r.result === "abandoned") return "";
    const submitted = r.submitted_moves || [];
    const opponent = r.opponent_moves || [];
    const sol = r.solution_moves || [];
    if (field === "agent") {
      const played = submitted[rowIndex];
      if (!played) return "";
      const expected = sol[rowIndex * 2];
      if (r.result === "correct" || played === expected) return " is-solved";
      if (r.result === "failed" && rowIndex === submitted.length - 1) {
        return " is-wrong";
      }
      if (played !== expected) return " is-wrong";
      return "";
    }
    const played = opponent[rowIndex];
    if (!played) return "";
    const expected = sol[rowIndex * 2 + 1];
    if (r.result === "correct" || played === expected) return " is-solved";
    return played !== expected ? " is-wrong" : "";
  }

  function setPosition(fen, animate, lastUci, opts) {
    const options = opts || {};
    annotations.clearAnnotations();
    const doAnimate = !!animate && lastFen != null && fen !== lastFen;
    const prevFen = lastFen;
    lastFen = fen;
    return board.setPosition(fen, doAnimate).then(() => {
      clearResultArrows();
      if (!options.skipLastMove) {
        paintLastMoveMarkers(
          board,
          lastUci || lastUciBetweenFens(prevFen, fen)
        );
      }
      if (options.resultArrows) {
        paintResultArrows(replay);
      }
    });
  }

  function lastUciForScanPly(n) {
    if (n < 0 || !replay || !replay.plies || !replay.plies[n]) return null;
    if (replay.plies[n].uci) return replay.plies[n].uci;
    const prevFen = n === 0 ? replay.start_fen : replay.plies[n - 1].fen;
    return lastUciBetweenFens(prevFen, replay.plies[n].fen);
  }

  function turnLabel() {
    const el = document.getElementById("board-label-turn");
    if (!el) return;
    if (puzzleSideToMove) {
      el.textContent = turnLabelFromSide(puzzleSideToMove);
      return;
    }
    el.textContent = "White to move";
  }

  function renderMeta(state) {
    const dl = document.getElementById("meta");
    if (dl) {
      dl.innerHTML = "<dt>Agent</dt><dd>" + escHtml(state.agent_name) + "</dd>";
    }
    const outcomeEl = document.getElementById("state-outcome");
    const diffEl = document.getElementById("state-difficulty");
    if (outcomeEl) outcomeEl.textContent = statusLabel(state);
    updateAgentWaitChip(state);
    if (diffEl) {
      diffEl.textContent =
        state.puzzle_rating > 0 ? String(state.puzzle_rating) : "—";
    }
  }

  function renderFinishedMeta(r) {
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
          ratingVal.textContent = String(Math.round(Number(agent.rating)));
        }
        if (devSub) {
          const rd = agent.deviation != null ? Number(agent.deviation) : null;
          if (rd != null && rd > 200) {
            devSub.textContent = " provisional";
            devSub.title =
              "Rating is provisional (high uncertainty; Glicko RD " + rd + ")";
          } else {
            devSub.textContent = "";
            devSub.title =
              rd != null ? "Glicko rating deviation (RD): " + rd : "";
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
    const solutionRows = solutionRowsFromState(state);

    let html = '<h3 class="moves-subhead">Played</h3>';
    if (!rows.length) {
      html += '<p style="color:var(--faint);margin:0">No moves yet.</p>';
    } else {
      html += moveHeaderHtml();
      html += rows
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
    pinScrollToBottom(mv);
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
            (wOn ? " w on" : " w") +
            (playedMoveClass(replay, i, "agent") ||
              (wWrong ? " is-wrong" : ""));
          const bCls =
            (bOn ? " b on" : " b") + playedMoveClass(replay, i, "opponent");
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
            '.</span><span class="w is-solved">' +
            escHtml(row.agent) +
            '</span><span class="b is-solved">' +
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
    const atTip =
      replay && replay.plies && scanPly >= replay.plies.length - 1;
    if (atTip) pinScrollToBottom(mv);
    else {
      const active = mv.querySelector(".on");
      if (active) active.scrollIntoView({ block: "center" });
    }
  }

  async function goToStep(index) {
    if (!replay || !replay.plies) return;
    const plies = replay.plies;
    const n = Math.max(-1, Math.min(index, plies.length - 1));
    scanPly = n;
    const failTip = replay.result === "failed" && n >= plies.length - 1;
    await setPosition(
      n < 0 ? replay.start_fen : plies[n].fen,
      true,
      failTip ? null : lastUciForScanPly(n),
      { skipLastMove: failTip, resultArrows: failTip }
    );
    turnLabel();
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
      cachePuzzleSide(replay);
      syncBoardOrientation(replay);
      scanPly = replay.plies ? replay.plies.length - 1 : -1;
      const failTip = replay.result === "failed" && scanPly >= 0;
      if (scanPly >= 0 && replay.plies.length) {
        await setPosition(
          replay.plies[scanPly].fen,
          true,
          failTip ? null : lastUciForScanPly(scanPly),
          { skipLastMove: failTip, resultArrows: failTip }
        );
      } else if (replay.start_fen) {
        await setPosition(replay.start_fen, false, null, {
          resultArrows: replay.result === "failed",
        });
      }
      turnLabel();
      renderFinishedMoves();
      renderFinishedMeta(replay);
      showPollError("");
    } catch (e) {
      showPollError("Could not load puzzle replay — is the server online?");
    }
  }

  function chainRowLabel(row, isCurrent) {
    const time = row.started_at
      ? new Date(row.started_at).toLocaleTimeString()
      : "";
    if (isCurrent) {
      return time ? time + " · this attempt" : "this attempt";
    }
    const moves = row.moves_played != null ? row.moves_played + " moves" : "—";
    return (time ? time + " · " : "") + statusLabel(row) + " · " + moves;
  }

  const chain = createWatchChain({
    attemptId: ATTEMPT_ID,
    attemptsPath: "/api/v1/puzzles/public/attempts",
    watchPrefix: "/p/",
    chainKind: "puzzle",
    rowLabel: chainRowLabel,
    getFinished: () => finished,
  });

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
      cachePuzzleSide(state);
      syncBoardOrientation(state);
      renderMeta(state);
      renderAgentMetrics(state);
      if (!finished) {
        renderLiveMoves(state);
      }
      if (state.status === "finished") {
        finished = true;
        stopPolling();
        await loadReplay();
        chain.startTracking(state);
      } else if (state.status === "abandoned") {
        finished = true;
        stopPolling();
        setPosition(state.fen, true);
        turnLabel();
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
        chain.startTracking(state);
      } else {
        setPosition(state.fen, true);
        turnLabel();
        chain.startTracking(state);
      }
      syncHeights();
      if (!finished) pinScrollToBottom(document.getElementById("mv"));
      showPollError("");
    } catch (e) {
      showPollError("Could not refresh puzzle state — is the server online?");
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

  function onPuzzleLayout() {
    syncHeights();
    if (!finished) pinScrollToBottom(document.getElementById("mv"));
  }

  window.addEventListener("resize", onPuzzleLayout);
  if (typeof ResizeObserver !== "undefined") {
    const wrap = document.getElementById("board-wrap");
    if (wrap) {
      const ro = new ResizeObserver(onPuzzleLayout);
      ro.observe(wrap);
    }
  }

  pollTimer = setInterval(poll, POLL_MS);
  poll();
}

main();
