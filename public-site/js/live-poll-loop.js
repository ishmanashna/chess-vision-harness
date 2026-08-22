/**
 * Chained setTimeout poll loop with tab-visibility pause and in-flight guard.
 * Phase 3: background tabs rest; slow ticks do not overlap.
 */

/** @returns {boolean} True when polls must not run or schedule (hidden tab). */
export function shouldPausePollWhenHidden(hidden) {
  return !!hidden;
}

/** @returns {boolean} True when a new tick must not start (previous tick still running). */
export function shouldSkipOverlappingPollTick(inFlight) {
  return !!inFlight;
}

/**
 * @param {object} options
 * @param {number} options.intervalMs
 * @param {() => void | Promise<void>} options.poll
 * @param {Document} [options.document]
 */
export function createLivePollLoop(options) {
  const intervalMs = options.intervalMs;
  const pollFn = options.poll;
  const doc =
    options.document ??
    (typeof document !== "undefined" ? document : null);

  let timer = null;
  let active = false;
  let inFlight = false;
  let pendingTick = false;
  let pausedByVisibility = doc ? shouldPausePollWhenHidden(doc.hidden) : false;

  function clearTimer() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function scheduleNext() {
    if (!active || pausedByVisibility || inFlight) return;
    clearTimer();
    timer = setTimeout(runTick, intervalMs);
  }

  function finishTick() {
    inFlight = false;
    if (!active || pausedByVisibility) return;
    if (pendingTick) {
      pendingTick = false;
      runTick();
      return;
    }
    scheduleNext();
  }

  async function runTick() {
    timer = null;
    if (!active || pausedByVisibility) return;
    if (shouldSkipOverlappingPollTick(inFlight)) {
      pendingTick = true;
      return;
    }
    inFlight = true;
    pendingTick = false;
    try {
      await pollFn();
    } catch (_e) {
      /* poll owns error UI */
    } finally {
      finishTick();
    }
  }

  function onVisibilityChange() {
    if (!active || !doc) return;
    const hidden = shouldPausePollWhenHidden(doc.hidden);
    if (hidden) {
      pausedByVisibility = true;
      pendingTick = false;
      clearTimer();
      return;
    }
    pausedByVisibility = false;
    if (!shouldSkipOverlappingPollTick(inFlight)) {
      runTick();
    } else {
      pendingTick = true;
    }
  }

  if (doc && typeof doc.addEventListener === "function") {
    doc.addEventListener("visibilitychange", onVisibilityChange);
  }

  return {
    start() {
      if (active) return;
      active = true;
      pausedByVisibility = doc ? shouldPausePollWhenHidden(doc.hidden) : false;
      if (!pausedByVisibility) runTick();
    },
    stop() {
      active = false;
      pendingTick = false;
      clearTimer();
    },
    isActive() {
      return active;
    },
    /** Test hook: mirror visibility without a real tab hide. */
    _setHiddenForTest(hidden) {
      if (!doc) return;
      doc.hidden = hidden;
      onVisibilityChange();
    },
    /** Test hook: whether a tick is in flight. */
    _isInFlight() {
      return inFlight;
    },
  };
}
