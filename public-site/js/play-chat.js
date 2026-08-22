/**
 * Play-page chat panel — poll transcript, send messages.
 */

import { bindLiveHealthGate } from "./live-health-gate.js";
import { createLivePollLoop } from "./live-poll-loop.js";

const CHAT_POLL_MS = 2500;

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderChatMessage(row) {
  const who = escapeHtml(row.from_label || row.from || "Player");
  const text = escapeHtml(row.text || "");
  const kind = row.from === "human" ? "is-human" : "is-agent";
  return (
    `<div class="play-chat-msg ${kind}" data-chat-seq="${row.seq}">` +
    `<span class="play-chat-who">${who}</span>` +
    `<span class="play-chat-text">${text}</span></div>`
  );
}

export function createPlayChat(root, api) {
  const panel = root.querySelector("[data-play-chat]");
  const logEl = root.querySelector("[data-chat-log]");
  const form = root.querySelector("[data-chat-form]");
  const input = root.querySelector("[data-chat-input]");
  const sendBtn = root.querySelector("[data-chat-send]");
  if (!panel || !logEl || !form || !input) {
    return { stop() {} };
  }

  let since = 0;
  let pollLoop = null;
  let busy = false;
  let hasMessages = false;

  function scrollToLatest() {
    logEl.scrollTop = logEl.scrollHeight;
  }

  function applyMessages(messages) {
    if (!messages || !messages.length) return;
    if (!hasMessages) {
      logEl.innerHTML = "";
      hasMessages = true;
    }
    for (const row of messages) {
      if (row.seq <= since) continue;
      logEl.insertAdjacentHTML("beforeend", renderChatMessage(row));
      since = Math.max(since, row.seq);
    }
    scrollToLatest();
  }

  async function pollChat() {
    if (busy || !pollLoop || !pollLoop.isActive()) return;
    try {
      const data = await api.fetchChat(since);
      applyMessages(data.messages);
    } catch (_err) {
      /* keep polling; position loop surfaces hard errors */
    }
  }

  function stopChatPolling() {
    if (pollLoop) pollLoop.stop();
  }

  function startChatPolling() {
    if (!pollLoop) {
      pollLoop = createLivePollLoop({ intervalMs: CHAT_POLL_MS, poll: pollChat });
    }
    if (!pollLoop.isActive()) pollLoop.start();
  }

  bindLiveHealthGate({
    onOnline: () => startChatPolling(),
    onOffline: () => stopChatPolling(),
  });

  async function sendMessage() {
    const text = input.value.trim();
    if (!text || busy) return;
    busy = true;
    if (sendBtn) sendBtn.disabled = true;
    try {
      const data = await api.postChat(text);
      input.value = "";
      if (data.message) {
        applyMessages([data.message]);
      } else {
        await pollChat();
      }
    } catch (err) {
      const status = root.querySelector("[data-play-error]");
      if (status) {
        status.textContent = err.message || "Chat failed";
        status.classList.add("is-visible");
      }
    } finally {
      busy = false;
      if (sendBtn) sendBtn.disabled = false;
      if (pollLoop && pollLoop.isActive()) startChatPolling();
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage();
  });

  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    sendMessage();
  });

  return {
    stop() {
      stopChatPolling();
    },
    refresh: pollChat,
  };
}
