/**
 * Human vs agent interactive play page (/play/{id}).
 */

import { createPlayApi, normalizeColor, readPlayToken } from "./play-api.js";
import { createPlayBoard } from "./play-board.js";

const POLL_WAIT_MS = 2500;

function gameIdFromPath() {
  const parts = window.location.pathname.replace(/\/+$/, "").split("/");
  return parts[parts.length - 1] || "";
}

function formatResult(result) {
  if (!result) return "Game over";
  if (result === "1/2-1/2") return "Draw";
  if (result === "1-0") return "White wins";
  if (result === "0-1") return "Black wins";
  return `Result: ${result}`;
}

function gameOverStatus(pos) {
  if (pos.end_reason === "inactivity" || pos.result === "*") {
    return pos.end_reason_label || "No result (idle timeout)";
  }
  const summary = formatResult(pos.result);
  if (pos.end_reason_label && pos.end_reason !== "inactivity") {
    return `${summary} — ${pos.end_reason_label}`;
  }
  return summary;
}

function statusText(pos) {
  if (pos.game_over) return gameOverStatus(pos);
  if (!pos.agent_joined) return "Waiting for agent…";
  if (pos.your_turn) return "Your turn";
  return "Agent's turn…";
}

function canHumanMove(pos) {
  return (
    !pos.game_over &&
    pos.agent_joined &&
    pos.your_turn
  );
}

function applyStatusUi(root, pos) {
  const statusEl = root.querySelector("[data-play-status]");
  const resignBtn = root.querySelector("[data-resign]");
  const boardWrap = root.querySelector("[data-board-wrap]");
  if (!statusEl) return;

  const text = statusText(pos);
  statusEl.textContent = text;
  statusEl.classList.remove("is-your-turn", "is-waiting", "is-over");
  if (pos.game_over) statusEl.classList.add("is-over");
  else if (!pos.agent_joined) statusEl.classList.add("is-waiting");
  else if (pos.your_turn) statusEl.classList.add("is-your-turn");

  if (resignBtn) resignBtn.disabled = !!pos.game_over;
  if (boardWrap) boardWrap.classList.toggle("is-disabled", !canHumanMove(pos));
}

function showError(root, message) {
  const el = root.querySelector("[data-play-error]");
  if (!el) return;
  if (message) {
    el.textContent = message;
    el.classList.add("is-visible");
  } else {
    el.textContent = "";
    el.classList.remove("is-visible");
  }
}

function updateMatchup(root, pos) {
  const el = root.querySelector("[data-play-matchup]");
  if (!el) return;
  const human = pos.human_nickname || "You";
  const agent = pos.agent_display_name || "Agent";
  el.innerHTML =
    `<strong>${escapeHtml(human)}</strong> vs <strong>${escapeHtml(agent)}</strong>` +
    ` · you play ${escapeHtml(normalizeColor(pos.human_color))}`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function main() {
  const root = document.querySelector("[data-play-root]");
  const mount = document.getElementById("play-board");
  if (!root || !mount) return;

  const gameId = gameIdFromPath();
  const token = readPlayToken();
  if (!token) {
    showError(root, "Missing play token. Open this page from Create Game.");
    return;
  }

  const api = createPlayApi(gameId, token);
  let pollTimer = null;
  let busy = false;
  let lastMoveCount = -1;

  const board = createPlayBoard(
    mount,
    "white",
    async (uci, _localFen) => {
      busy = true;
      showError(root, "");
      try {
        const res = await api.postMove(uci);
        await syncFromServer(res, true);
        return true;
      } catch (err) {
        showError(root, err.message || "Move rejected");
        await refreshPosition(true);
        return false;
      } finally {
        busy = false;
        schedulePoll();
      }
    }
  );

  async function syncFromServer(pos, animate) {
    const human = normalizeColor(pos.human_color);
    board.setHumanColor(human);
    board.syncLegalUci(pos.legal_moves_uci);
    await board.setPosition(pos.fen, animate);
    applyStatusUi(root, pos);
    updateMatchup(root, pos);
    board.applyInputState(canHumanMove(pos));
    lastMoveCount = pos.move_count ?? lastMoveCount;
  }

  async function refreshPosition(forceAnimate) {
    const pos = await api.fetchPosition();
    const animate =
      forceAnimate ||
      (lastMoveCount >= 0 && pos.move_count !== lastMoveCount);
    await syncFromServer(pos, animate);
    return pos;
  }

  function schedulePoll() {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(pollLoop, POLL_WAIT_MS);
  }

  async function pollLoop() {
    if (busy) {
      schedulePoll();
      return;
    }
    try {
      const pos = await refreshPosition(false);
      if (pos.game_over) {
        pollTimer = null;
        return;
      }
      pollTimer = setTimeout(pollLoop, POLL_WAIT_MS);
    } catch (err) {
      showError(root, err.message || "Could not reach game server");
      pollTimer = setTimeout(pollLoop, POLL_WAIT_MS);
    }
  }

  const resignBtn = root.querySelector("[data-resign]");
  if (resignBtn) {
    resignBtn.addEventListener("click", async () => {
      if (!window.confirm("Resign this game?")) return;
      busy = true;
      resignBtn.disabled = true;
      showError(root, "");
      try {
        await api.postResign();
        await refreshPosition(false);
      } catch (err) {
        showError(root, err.message || "Resign failed");
        resignBtn.disabled = false;
      } finally {
        busy = false;
        schedulePoll();
      }
    });
  }

  try {
    await refreshPosition(false);
    schedulePoll();
  } catch (err) {
    showError(root, err.message || "Could not load game");
  }
}

document.addEventListener("DOMContentLoaded", main);
