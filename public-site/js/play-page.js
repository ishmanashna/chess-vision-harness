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
import { bindLiveHealthGate } from "./live-health-gate.js";
import { createLivePollLoop } from "./live-poll-loop.js";

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

  const copyBtn = document.querySelector("[data-copy-game-id]");
  const copyHint = document.querySelector("[data-copy-game-hint]");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      if (!gameId) {
        if (copyHint) copyHint.textContent = "No game ID";
        return;
      }
      navigator.clipboard.writeText(gameId).then(() => {
        if (!copyHint) return;
        copyHint.textContent = "ID copied";
        setTimeout(() => {
          if (copyHint.textContent === "ID copied") copyHint.textContent = "";
        }, 2000);
      });
    });
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
  const chat = createPlayChat(root, api);
  const syncTabAttention = createTabAttention(document.title);
  let positionPollLoop = null;
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
        ensurePositionPolling();
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
    if (pos.game_over) {
      stopPositionPolling();
      chat.stop();
    }
  }

  async function refreshPosition(forceAnimate) {
    const pos = await api.fetchPosition();
    const animate =
      forceAnimate ||
      (lastMoveCount >= 0 && pos.move_count !== lastMoveCount);
    await syncFromServer(pos, animate);
    return pos;
  }

  function stopPositionPolling() {
    if (positionPollLoop) positionPollLoop.stop();
  }

  async function pollPosition() {
    if (busy) return;
    try {
      const pos = await refreshPosition(false);
      if (pos.game_over) {
        stopPositionPolling();
        chat.stop();
      }
    } catch (err) {
      showError(root, err.message || "Could not reach game server");
    }
  }

  function ensurePositionPolling() {
    if (!positionPollLoop) {
      positionPollLoop = createLivePollLoop({
        intervalMs: POLL_WAIT_MS,
        poll: pollPosition,
      });
    }
    if (!positionPollLoop.isActive()) positionPollLoop.start();
  }

  async function startPositionPolling() {
    try {
      await refreshPosition(false);
      ensurePositionPolling();
    } catch (err) {
      showError(root, err.message || "Could not load game");
    }
  }

  bindLiveHealthGate({
    onOnline: () => startPositionPolling(),
    onOffline: () => {
      stopPositionPolling();
      showError(
        root,
        "Game server is offline — try again when the operator is online."
      );
    },
  });

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
        ensurePositionPolling();
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
      ensurePositionPolling();
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
}

document.addEventListener("DOMContentLoaded", main);
