/**
 * Play page status, matchup, move list, and tab-attention UI.
 */

import { normalizeColor } from "./play-api.js";
import { canPremove } from "./play-premove.js";
import { syncDownloadButton } from "./play-export.js";

const FAVICON_DEFAULT = "/favicon.svg";
const FAVICON_ALERT = "/favicon-alert.svg";

function formatResult(result) {
  if (!result) return "Game over";
  if (result === "1/2-1/2") return "Draw";
  if (result === "1-0") return "White wins";
  if (result === "0-1") return "Black wins";
  return `Result: ${result}`;
}

export function gameOverStatus(pos) {
  if (pos.end_reason === "inactivity" || pos.result === "*") {
    return pos.end_reason_label || "No result (idle timeout)";
  }
  const summary = formatResult(pos.result);
  if (pos.end_reason_label && pos.end_reason !== "inactivity") {
    return `${summary} — ${pos.end_reason_label}`;
  }
  return summary;
}

export function statusText(pos) {
  if (pos.game_over) return gameOverStatus(pos);
  if (!pos.agent_joined) return "Waiting for agent…";
  if (pos.your_turn) return "Your turn";
  return "Agent's turn…";
}

export function applyStatusUi(root, pos) {
  const statusEl = root.querySelector("[data-play-status]");
  const resignBtn = root.querySelector("[data-resign]");
  const drawOfferBtn = root.querySelector("[data-draw-offer]");
  const drawAcceptBtn = root.querySelector("[data-draw-accept]");
  const drawDeclineBtn = root.querySelector("[data-draw-decline]");
  const boardWrap = root.querySelector("[data-board-wrap]");
  if (!statusEl) return;

  const text = statusText(pos);
  statusEl.textContent = text;
  statusEl.classList.remove("is-your-turn", "is-waiting", "is-over");
  if (pos.game_over) statusEl.classList.add("is-over");
  else if (!pos.agent_joined) statusEl.classList.add("is-waiting");
  else if (pos.your_turn) statusEl.classList.add("is-your-turn");

  if (resignBtn) resignBtn.disabled = !!pos.game_over;
  if (drawOfferBtn) {
    drawOfferBtn.disabled = !!pos.game_over || !pos.can_offer_draw;
    drawOfferBtn.hidden = !!pos.game_over;
  }
  if (drawAcceptBtn) {
    const show = !pos.game_over && !!pos.can_respond_draw;
    drawAcceptBtn.hidden = !show;
    drawAcceptBtn.disabled = !show;
  }
  if (drawDeclineBtn) {
    const show = !pos.game_over && !!pos.can_respond_draw;
    drawDeclineBtn.hidden = !show;
    drawDeclineBtn.disabled = !show;
  }
  if (boardWrap) {
    boardWrap.classList.toggle("is-waiting-turn", canPremove(pos));
  }
  syncDownloadButton(root, pos);
}

export function showError(root, message) {
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

function formatAgentElo(pos) {
  if (pos.agent_elo == null || pos.agent_elo === "") return "";
  if (window.CVH && typeof window.CVH.formatElo === "function") {
    return window.CVH.formatElo({ elo: pos.agent_elo });
  }
  return String(pos.agent_elo);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function updateMatchup(root, pos) {
  const el = root.querySelector("[data-play-matchup]");
  if (!el) return;
  const human = pos.human_nickname || "You";
  const agent = pos.agent_display_name || "Agent";
  const elo = formatAgentElo(pos);
  const agentLabel = elo ? `${agent} (${elo})` : agent;
  const colorPart = pos.human_color
    ? ` · you play ${escapeHtml(normalizeColor(pos.human_color))}`
    : "";
  el.innerHTML =
    `<strong>${escapeHtml(human)}</strong> vs <strong>${escapeHtml(agentLabel)}</strong>` +
    colorPart;
}

export function renderMoveList(root, pos, lastRenderedCount) {
  const el = root.querySelector("[data-play-moves]");
  if (!el) return lastRenderedCount;
  const plies = pos.move_count ?? 0;
  const rows = pos.move_rows;
  if (!rows || !rows.length) {
    if (lastRenderedCount !== 0) {
      el.innerHTML = '<p class="play-placeholder">No moves yet.</p>';
    }
    return 0;
  }
  if (plies === lastRenderedCount && el.querySelector(".move-row")) {
    return lastRenderedCount;
  }
  el.innerHTML = rows
    .map((row) => {
      const wOn = row.num * 2 - 1 === plies;
      const bOn = row.num * 2 === plies;
      return (
        `<div class="move-row"><span class="mn">${row.num}.</span>` +
        `<span class="w${wOn ? " on" : ""}">${escapeHtml(row.white)}</span>` +
        `<span class="b${bOn ? " on" : ""}">${escapeHtml(row.black || "")}</span></div>`
      );
    })
    .join("");
  const on = el.querySelector(".on");
  if (on) on.scrollIntoView({ block: "nearest" });
  return plies;
}

export function createTabAttention(defaultTitle) {
  let lastYourTurn = null;
  let faviconLink = null;

  function setFavicon(href) {
    if (!faviconLink) {
      faviconLink = document.querySelector('link[rel="icon"][data-play-dynamic]');
      if (!faviconLink) {
        faviconLink = document.createElement("link");
        faviconLink.rel = "icon";
        faviconLink.type = "image/svg+xml";
        faviconLink.setAttribute("data-play-dynamic", "1");
        document.head.appendChild(faviconLink);
      }
    }
    faviconLink.href = href;
  }

  return function syncTabAttention(pos) {
    const yourTurn = !pos.game_over && pos.agent_joined && !!pos.your_turn;
    if (lastYourTurn === yourTurn) return;
    const prev = lastYourTurn;
    lastYourTurn = yourTurn;

    if (yourTurn && prev === false) {
      document.title = "★ Your turn — Play";
      setFavicon(FAVICON_ALERT);
    } else if (!yourTurn || pos.game_over) {
      document.title = defaultTitle;
      setFavicon(FAVICON_DEFAULT);
    }
  };
}
