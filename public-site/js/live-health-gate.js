/**
 * Gate proxied live API polls on edge health (Online vs Sleeping).
 * Phase 2: skip /api/games and /api/v1 proxied fetches when origin is down.
 */

export function shouldFetchLive(health) {
  return !!(health && health.online);
}

/**
 * Subscribe to CVH health and invoke onOnline / onOffline when live fetch is allowed.
 * Uses checkEdgeHealth() default cache — does not force a probe.
 */
export function bindLiveHealthGate(callbacks) {
  const onOnline = callbacks && callbacks.onOnline;
  const onOffline = callbacks && callbacks.onOffline;
  let allowed = false;
  let initialized = false;

  function apply(health, meta) {
    const next = shouldFetchLive(health);
    const was = allowed;
    allowed = next;
    if (next) {
      if (!was || (meta && meta.becameOnline)) {
        if (onOnline) onOnline(health, meta || {});
      }
    } else if (was || !initialized) {
      if (onOffline) onOffline(health, meta || {});
    }
    initialized = true;
  }

  const cvh = typeof window !== "undefined" && window.CVH;
  if (cvh && typeof cvh.checkEdgeHealth === "function") {
    cvh.checkEdgeHealth().then(function (h) {
      apply(h, { becameOnline: false });
    });
    if (typeof cvh.onHealthUi === "function") {
      cvh.onHealthUi(function (h, meta) {
        apply(h, meta || {});
      });
    }
  } else {
    apply({ online: true }, { becameOnline: false });
  }

  return {
    isAllowed: function () {
      return allowed;
    },
  };
}
