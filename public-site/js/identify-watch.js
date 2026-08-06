/**
 * Public board-identification watch/replay page (/i/{id}).
 * Live: poll the observer-safe public state and render the visible board.
 * After submission: unlock the placement review — the answer board overlay
 * (green = exact, red = mismatch) and the per-square table (submitted vs
 * expected). Observers never see the true placement while the attempt is
 * active.
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
  const idx = parts.indexOf("i");
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
    const accEl = document.getElementById("state-accuracy");
    const subEl = document.getElementById("state-submitted");
    const diffEl = document.getElementById("state-difficulty");
    if (statusEl) statusEl.textContent = statusLabel(state);
    if (resultEl) resultEl.textContent = state.result || "—";
    if (accEl) accEl.textContent = fmtAccuracy(state.accuracy);
    if (subEl) subEl.textContent = String(state.submitted_count);
    if (diffEl) {
      diffEl.textContent = state.difficulty != null ? String(state.difficulty) : "—";
    }
  }

  function renderReplay() {
    const panel = document.getElementById("replay-panel");
    const body = document.getElementById("results-body");
    if (!panel || !body || !replay) return;
    panel.hidden = false;
    const rows = replyRows(replay);
    body.innerHTML = rows
      .map(
        (r) =>
          '<tr><td>' +
          escHtml(r.square) +
          "</td><td>" +
          escHtml(r.expected || "—") +
          "</td><td>" +
          escHtml(r.submitted || "—") +
          '</td><td><span class="badge ' +
          r.status +
          '">' +
          escHtml(r.status.replace("_", " ")) +
          "</span></td></tr>"
      )
      .join("");
    const wrap = document.getElementById("answer-wrap");
    if (wrap) {
      wrap.style.display = "block";
      const img = document.getElementById("answer-img");
      if (img) {
        img.src = "/i/" + encodeURIComponent(ATTEMPT_ID) + "/answer.png?" + Date.now();
      }
    }
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

  async function loadReplay() {
    try {
      const r = await fetch(
        "/api/v1/identify/public/" + encodeURIComponent(ATTEMPT_ID) + "/replay"
      );
      if (!r.ok) return;
      replay = await r.json();
      renderReplay();
    } catch (e) {
      /* ignore */
    }
  }

  async function poll() {
    try {
      const r = await fetch(
        "/api/v1/identify/public/" + encodeURIComponent(ATTEMPT_ID)
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

  pollTimer = setInterval(poll, POLL_MS);
  poll();
}

main();