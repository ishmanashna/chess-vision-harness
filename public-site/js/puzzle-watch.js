/**
 * Public puzzle watch/replay page (/p/{id}).
 * Live: poll the observer-safe public state and render the current board.
 * Replay: after the attempt ends, unlock the per-ply steps (solution shown).
 * Observers never see submitted moves or solution data while active.
 */

import {
  Chessboard,
  COLOR,
  BORDER_TYPE,
} from "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/src/Chessboard.js";

const BOARD_ASSETS =
  "https://cdn.jsdelivr.net/npm/cm-chessboard@8.7.2/assets/";
const POLL_MS = 3000;

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

async function main() {
  const ATTEMPT_ID = attemptIdFromPage();
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
  let replayIndex = -1;
  let pollTimer = null;

  function setPosition(fen, animate) {
    const doAnimate = !!animate && lastFen != null && fen !== lastFen;
    lastFen = fen;
    return board.setPosition(fen, doAnimate);
  }

  function renderMeta(state) {
    const meta = document.getElementById("meta");
    if (meta) {
      meta.innerHTML =
        "<dt>Attempt</dt><dd>" +
        escHtml(state.attempt_id) +
        '</dd><dt>Agent</dt><dd>' +
        escHtml(state.agent_name) +
        "</dd>";
    }
    const statusEl = document.getElementById("state-status");
    const resultEl = document.getElementById("state-result");
    const movesEl = document.getElementById("state-moves");
    const ratingEl = document.getElementById("state-rating");
    const themesEl = document.getElementById("state-themes");
    if (statusEl) statusEl.textContent = statusLabel(state);
    if (resultEl) resultEl.textContent = state.result || "—";
    if (movesEl) movesEl.textContent = String(state.moves_played);
    if (ratingEl) ratingEl.textContent = String(state.puzzle_rating || "—");
    if (themesEl) {
      themesEl.innerHTML =
        state.themes && state.themes.length
          ? state.themes
              .map((t) => '<span class="theme-tag">' + escHtml(t) + "</span>")
              .join("")
          : '<span style="color:var(--faint)">—</span>';
    }
    const turnEl = document.getElementById("board-label-turn");
    if (turnEl) turnEl.textContent = sideToMoveFromFen(state.fen);
  }

  function renderReplay() {
    const panel = document.getElementById("replay-panel");
    const steps = document.getElementById("replay-steps");
    const pos = document.getElementById("replay-pos");
    if (!panel || !steps) return;
    panel.hidden = false;
    const plies = replay.plies || [];
    steps.innerHTML =
      '<button type="button" class="step-chip' +
      (replayIndex < 0 ? " on" : "") +
      '" data-step="-1">Start</button>' +
      plies
        .map(
          (p, i) =>
            '<button type="button" class="step-chip' +
            (i === replayIndex ? " on" : "") +
            '" data-step="' +
            i +
            '">' +
            escHtml(p.label) +
            "</button>"
        )
        .join("");
    if (pos) {
      pos.textContent =
        replayIndex < 0
          ? "0 / " + plies.length
          : replayIndex + 1 + " / " + plies.length;
    }
    steps.querySelectorAll("[data-step]").forEach((btn) => {
      btn.addEventListener("click", () => {
        goToStep(Number(btn.getAttribute("data-step")));
      });
    });
    const prevBtn = document.getElementById("replay-prev");
    const nextBtn = document.getElementById("replay-next");
    if (prevBtn) prevBtn.disabled = replayIndex < 0;
    if (nextBtn) nextBtn.disabled = replayIndex >= plies.length - 1;
    renderFirstWrongStep(plies);
  }

  function renderFirstWrongStep(plies) {
    if (!replay || replay.result !== "failed" || !replay.first_wrong_move) return;
    const steps = document.getElementById("replay-steps");
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "step-chip is-wrong";
    chip.textContent = "✗ " + replay.first_wrong_move;
    chip.title = "First wrong move (attempt ended)";
    steps.appendChild(chip);
  }

  function goToStep(index) {
    const plies = replay.plies || [];
    const n = Math.max(-1, Math.min(index, plies.length - 1));
    replayIndex = n;
    const fen = n < 0 ? replay.start_fen : plies[n].fen;
    setPosition(fen, true);
    renderReplay();
    const turnEl = document.getElementById("board-label-turn");
    if (turnEl) turnEl.textContent = sideToMoveFromFen(fen);
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
      replayIndex = replay.plies ? replay.plies.length - 1 : -1;
      if (replayIndex >= 0 && replay.plies.length) {
        setPosition(replay.plies[replayIndex].fen, true);
      }
      renderReplay();
    } catch (e) {
      /* ignore */
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
      setPosition(state.fen, true);
      if (state.status === "finished") {
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
        await loadReplay();
      } else if (state.status === "abandoned") {
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      }
    } catch (e) {
      /* ignore */
    }
  }

  const prevBtn = document.getElementById("replay-prev");
  const nextBtn = document.getElementById("replay-next");
  if (prevBtn) prevBtn.addEventListener("click", () => goToStep(replayIndex - 1));
  if (nextBtn) nextBtn.addEventListener("click", () => goToStep(replayIndex + 1));

  pollTimer = setInterval(poll, POLL_MS);
  poll();
}

main();
