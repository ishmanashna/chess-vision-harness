/**
 * Human vs agent interactive play page (/play/{id}).
 */

import { createPlayApi, normalizeColor, readPlayToken } from "./play-api.js";
import { createPlayBoard } from "./play-board.js";
import { createPlayChat } from "./play-chat.js";
import { lastUciFromMoveRows } from "./board-last-move.js";
import { setupBoardDownload } from "./play-export.js";
import { canPremove, tryFirePremove } from "./play-premove.js";
import {
  applyStatusUi,
  createTabAttention,
  renderMoveList,
  showError,
  updateMatchup,
} from "./play-page-ui.js";

const POLL_WAIT_MS = 2500;

function gameIdFromPath() {
  const parts = window.location.pathname.replace(/\/+$/, "").split("/");
  const idx = parts.indexOf("play");
  const id = idx >= 0 ? parts[idx + 1] : parts[parts.length - 1] || "";
  if (!id || id === "index.html" || id === "play") return "";
  return id;
}

function wirePlayShellChrome(gameId) {
  const spectate = document.querySelector("[data-spectate-link]");
  if (spectate && gameId) {
    spectate.href = "/g/" + encodeURIComponent(gameId);
  }
}

function canHumanMove(pos) {
  return (
    !pos.game_over &&
    pos.agent_joined &&
    pos.your_turn
  );
}

function syncHumanGameRegistry(gameId, token, pos) {
  const registry = window.CVH && window.CVH.humanGames;
  if (!registry) return;
  if (pos.game_over) {
    registry.remove(gameId);
  } else {
    registry.upsert({
      gameId,
      token,
      nickname: pos.human_nickname || "",
      agentName: pos.agent_display_name || "",
    });
  }
  if (window.CVH.refreshHumanGamesLists) window.CVH.refreshHumanGamesLists();
}

async function main() {
  const root = document.querySelector("[data-play-root]");
  const mount = document.getElementById("play-board");
  if (!root || !mount) return;

  const gameId = gameIdFromPath();
  wirePlayShellChrome(gameId);
  const token = readPlayToken(gameId);
  if (!token) {
    showError(root, "Missing play token. Open this page from Create Game.");
    return;
  }

  const api = createPlayApi(gameId, token);
  createPlayChat(root, api);
  const syncTabAttention = createTabAttention(document.title);
  let pollTimer = null;
  let busy = false;
  let lastMoveCount = -1;
  let lastRenderedMoveCount = -1;
  let cachedHumanColor = null;
  let lastFen = null;
  let prevYourTurn = null;

  let board = null;
  function syncClearPremoveBtn() {
    const btn = root.querySelector("[data-clear-premove]");
    if (!btn || !board) return;
    const has = !!board.getPremove();
    btn.hidden = !has;
    btn.disabled = !has;
  }

  board = createPlayBoard(
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
    },
    syncClearPremoveBtn
  );

  async function syncFromServer(pos, animate) {
    if (pos.game_over && board.getPremove()) {
      board.clearPremove();
    }

    if (pos.human_color) {
      const human = normalizeColor(pos.human_color);
      if (human !== cachedHumanColor) {
        board.setHumanColor(human);
        cachedHumanColor = human;
      }
    }
    board.syncLegalUci(pos.legal_moves_uci);
    if (pos.fen && pos.fen !== lastFen) {
      const lastUci = lastUciFromMoveRows(pos.move_rows, pos.move_count);
      await board.setPosition(pos.fen, animate, lastUci);
      lastFen = pos.fen;
    }

    const turnEdge = prevYourTurn === false && !!pos.your_turn;
    if (turnEdge && board.getPremove() && !busy) {
      busy = true;
      try {
        const fired = await tryFirePremove(board, api, pos, prevYourTurn);
        if (fired) {
          lastFen = fired.fen || lastFen;
          await syncFromServer(fired, true);
          return;
        }
      } catch (err) {
        showError(root, err.message || "Premove rejected");
        await refreshPosition(true);
        return;
      } finally {
        busy = false;
      }
    }

    applyStatusUi(root, pos);
    updateMatchup(root, pos);
    const inputErr = board.syncInputState(canHumanMove(pos), canPremove(pos));
    if (inputErr) showError(root, inputErr);
    syncClearPremoveBtn();
    lastRenderedMoveCount = renderMoveList(root, pos, lastRenderedMoveCount);
    syncTabAttention(pos);
    prevYourTurn = !!pos.your_turn;
    lastMoveCount = pos.move_count ?? lastMoveCount;
    syncHumanGameRegistry(gameId, token, pos);
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

  async function drawAction(fn, errLabel) {
    busy = true;
    showError(root, "");
    try {
      const res = await fn();
      await syncFromServer(res, false);
    } catch (err) {
      showError(root, err.message || errLabel);
      await refreshPosition(false);
    } finally {
      busy = false;
      schedulePoll();
    }
  }

  const drawOfferBtn = root.querySelector("[data-draw-offer]");
  if (drawOfferBtn) {
    drawOfferBtn.addEventListener("click", () => drawAction(api.postDrawOffer, "Draw offer failed"));
  }
  const drawAcceptBtn = root.querySelector("[data-draw-accept]");
  if (drawAcceptBtn) {
    drawAcceptBtn.addEventListener("click", () => {
      if (!window.confirm("Accept draw?")) return;
      drawAction(api.postDrawAccept, "Accept draw failed");
    });
  }
  const drawDeclineBtn = root.querySelector("[data-draw-decline]");
  if (drawDeclineBtn) {
    drawDeclineBtn.addEventListener("click", () => drawAction(api.postDrawDecline, "Decline draw failed"));
  }

  const clearPremoveBtn = root.querySelector("[data-clear-premove]");
  if (clearPremoveBtn) {
    clearPremoveBtn.addEventListener("click", () => {
      board.clearPremove();
      syncClearPremoveBtn();
    });
  }

  setupBoardDownload(root, board, api, gameId);

  try {
    await refreshPosition(false);
    schedulePoll();
  } catch (err) {
    showError(root, err.message || "Could not load game");
  }
}

document.addEventListener("DOMContentLoaded", main);
