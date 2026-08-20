/**
 * Shared attempt-chain panel, polling, and live-follow for puzzle and identify watch pages.
 */

const CHAIN_POLL_MS = 15000;
const CHAIN_POLL_FINISHED_MS = 5000;
const FOLLOW_DELAY_MS = 5000;

export function watchHrefForRow(row, prefix) {
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

function stayStorageKey(chainKind, agentKey, agentName) {
  const agent = agentKey || agentName;
  if (!agent) return null;
  return "chess-harness-chain-stay:" + chainKind + ":" + agent;
}

/**
 * @param {object} options
 * @param {string} options.attemptId
 * @param {string} options.attemptsPath - e.g. /api/v1/puzzles/public/attempts
 * @param {string} options.watchPrefix - /p/ or /i/
 * @param {"puzzle"|"identify"} options.chainKind
 * @param {(row: object, isCurrent: boolean) => string} options.rowLabel
 * @param {() => boolean} options.getFinished
 */
export function createWatchChain(options) {
  const {
    attemptId,
    attemptsPath,
    watchPrefix,
    chainKind,
    rowLabel,
    getFinished,
  } = options;

  let chainTimer = null;
  let agentKey = null;
  let agentName = null;
  let chainRows = [];
  let followCancelled = false;
  let followTimeout = null;
  let followCountdownTimer = null;
  let followTargetId = null;
  let stayLoaded = false;

  function loadStayFromSession() {
    if (stayLoaded) return;
    stayLoaded = true;
    const key = stayStorageKey(chainKind, agentKey, agentName);
    if (key && sessionStorage.getItem(key) === "1") {
      followCancelled = true;
    }
  }

  function persistStay() {
    const key = stayStorageKey(chainKind, agentKey, agentName);
    if (key) sessionStorage.setItem(key, "1");
    followCancelled = true;
  }

  function currentChainIndex(rows) {
    return rows.findIndex((row) => row.attempt_id === attemptId);
  }

  function clearFollowTimers() {
    if (followTimeout) {
      clearTimeout(followTimeout);
      followTimeout = null;
    }
    if (followCountdownTimer) {
      clearInterval(followCountdownTimer);
      followCountdownTimer = null;
    }
  }

  function hideFollowBanner() {
    const banner = document.getElementById("follow-banner");
    if (banner) banner.classList.remove("is-visible");
    clearFollowTimers();
    followTargetId = null;
  }

  function scheduleAutoFollow(newestRow) {
    if (followCancelled || !newestRow) return;
    if (newestRow.status !== "active") {
      hideFollowBanner();
      return;
    }
    if (newestRow.attempt_id === attemptId) {
      hideFollowBanner();
      return;
    }
    const href = watchHrefForRow(newestRow, watchPrefix);
    if (!href) return;
    if (followTargetId === newestRow.attempt_id && followTimeout) return;

    followTargetId = newestRow.attempt_id;
    const banner = document.getElementById("follow-banner");
    const countdownEl = document.getElementById("follow-countdown");
    if (banner) banner.classList.add("is-visible");

    let secs = Math.round(FOLLOW_DELAY_MS / 1000);
    if (countdownEl) countdownEl.textContent = String(secs);

    clearFollowTimers();
    followCountdownTimer = setInterval(() => {
      secs -= 1;
      if (countdownEl) countdownEl.textContent = String(Math.max(0, secs));
      if (secs <= 0 && followCountdownTimer) {
        clearInterval(followCountdownTimer);
        followCountdownTimer = null;
      }
    }, 1000);

    followTimeout = setTimeout(() => {
      if (!followCancelled) location.assign(href);
    }, FOLLOW_DELAY_MS);
  }

  function renderChain(rows, opts) {
    const panel = document.getElementById("chain-panel");
    const empty = document.getElementById("chain-empty");
    const indexEl = document.getElementById("chain-index");
    const currentEl = document.getElementById("chain-current");
    const newerBtn = document.getElementById("chain-newer");
    const olderBtn = document.getElementById("chain-older");
    if (!panel || !empty) return;

    if (opts && opts.error) {
      panel.hidden = true;
      empty.hidden = false;
      empty.textContent = opts.error;
      return;
    }

    const all = (rows || []).slice();
    chainRows = all;
    if (!all.length) {
      panel.hidden = true;
      empty.hidden = false;
      empty.textContent = "No attempts in this chain yet.";
      return;
    }

    empty.hidden = true;
    panel.hidden = false;

    const idx = currentChainIndex(all);
    const pos = idx >= 0 ? idx + 1 : 1;
    if (indexEl) indexEl.textContent = pos + " of " + all.length;

    const currentRow = idx >= 0 ? all[idx] : all[0];
    if (currentEl) {
      currentEl.textContent = rowLabel(currentRow, idx >= 0);
    }

    if (newerBtn) {
      newerBtn.disabled = idx <= 0;
    }
    if (olderBtn) {
      olderBtn.disabled = idx < 0 || idx >= all.length - 1;
    }

    const newest = all[0];
    if (newest && newest.status === "active" && newest.attempt_id !== attemptId) {
      scheduleAutoFollow(newest);
    } else {
      hideFollowBanner();
    }
  }

  function navigateChain(delta) {
    const idx = currentChainIndex(chainRows);
    if (idx < 0) return;
    const target = chainRows[idx + delta];
    if (!target) return;
    const href = watchHrefForRow(target, watchPrefix);
    if (!href) return;
    persistStay();
    location.assign(href);
  }

  function setChainPollInterval(ms) {
    if (chainTimer) clearInterval(chainTimer);
    chainTimer = setInterval(refreshChain, ms);
  }

  async function refreshChain() {
    const keyParam = agentKey
      ? "by_key=" + encodeURIComponent(agentKey)
      : agentName
        ? "by_agent=" + encodeURIComponent(agentName)
        : null;
    if (!keyParam) return;
    try {
      const r = await fetch(attemptsPath + "?" + keyParam + "&limit=50");
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

  function startTracking(state) {
    agentKey = state.key || agentKey;
    agentName = state.agent_name || agentName;
    if (!agentKey && !agentName) return;
    loadStayFromSession();
    const finished = getFinished();
    const interval = finished ? CHAIN_POLL_FINISHED_MS : CHAIN_POLL_MS;
    if (!chainTimer) {
      setChainPollInterval(interval);
      refreshChain();
    } else if (finished) {
      setChainPollInterval(interval);
      refreshChain();
    }
  }

  const newerBtn = document.getElementById("chain-newer");
  const olderBtn = document.getElementById("chain-older");
  if (newerBtn) newerBtn.onclick = () => navigateChain(-1);
  if (olderBtn) olderBtn.onclick = () => navigateChain(1);

  const followStay = document.getElementById("follow-stay");
  if (followStay) {
    followStay.onclick = () => {
      persistStay();
      hideFollowBanner();
    };
  }

  return { startTracking };
}
