/**
 * Last-known-good public leaderboards on Pages.
 *
 * Live proxy responses are stored in the Cache API while the origin is Online.
 * Sleeping clients read /api/leaderboard/snapshot (never the origin) so they
 * get that copy instead of a weeks-old git bake. Static /data JSON is the
 * fallback when the cache is empty.
 */

export const LEADERBOARD_SPECS = {
  "/api/leaderboard/live": {
    snapshotPath: "/api/leaderboard/snapshot",
    assetPath: "/data/leaderboard.json",
    cachePath: "/__cvh-cache/leaderboard-live",
  },
  "/api/leaderboard/puzzles/live": {
    snapshotPath: "/api/leaderboard/puzzles/snapshot",
    assetPath: "/data/puzzles_leaderboard.json",
    cachePath: "/__cvh-cache/puzzles-leaderboard-live",
  },
  "/api/leaderboard/identify/live": {
    snapshotPath: "/api/leaderboard/identify/snapshot",
    assetPath: "/data/identify_leaderboard.json",
    cachePath: "/__cvh-cache/identify-leaderboard-live",
  },
};

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

const CACHE_STORE_CONTROL = "public, max-age=2592000";

/**
 * @param {string} pathname
 * @returns {boolean}
 */
export function isLeaderboardLivePath(pathname) {
  return Object.prototype.hasOwnProperty.call(LEADERBOARD_SPECS, pathname);
}

/**
 * @param {string} pathname
 * @returns {boolean}
 */
export function isLeaderboardSnapshotPath(pathname) {
  return Boolean(specForSnapshotPath(pathname));
}

/**
 * Pages-owned /api paths that must not be collapsed into the unknown-API 404.
 * @param {string} pathname
 * @returns {boolean}
 */
export function isPagesOwnedApiPath(pathname) {
  return pathname === "/api/edge-health" || isLeaderboardSnapshotPath(pathname);
}

/**
 * @param {string} pathname
 * @returns {{ livePath: string, snapshotPath: string, assetPath: string, cachePath: string } | null}
 */
export function specForSnapshotPath(pathname) {
  for (const [livePath, spec] of Object.entries(LEADERBOARD_SPECS)) {
    if (spec.snapshotPath === pathname) {
      return { livePath, ...spec };
    }
  }
  return null;
}

/**
 * @param {unknown} payload
 * @returns {number}
 */
export function snapshotGeneratedAtMs(payload) {
  if (!payload || typeof payload !== "object") {
    return 0;
  }
  const generated = /** @type {{ generated_at?: unknown }} */ (payload).generated_at;
  if (typeof generated !== "string") {
    return 0;
  }
  const ms = Date.parse(generated);
  return Number.isFinite(ms) ? ms : 0;
}

/**
 * @param {object | null | undefined} a
 * @param {object | null | undefined} b
 * @returns {object | null | undefined}
 */
export function preferNewerSnapshot(a, b) {
  if (!a) return b;
  if (!b) return a;
  return snapshotGeneratedAtMs(a) >= snapshotGeneratedAtMs(b) ? a : b;
}

/**
 * @param {unknown} payload
 * @returns {boolean}
 */
export function isLeaderboardPayload(payload) {
  if (!payload || typeof payload !== "object") {
    return false;
  }
  const row = /** @type {{ generated_at?: unknown, agents?: unknown }} */ (payload);
  return typeof row.generated_at === "string" && Array.isArray(row.agents);
}

/**
 * @param {string} requestUrl
 * @param {string} livePath
 * @returns {Request}
 */
export function leaderboardCacheRequest(requestUrl, livePath) {
  const spec = LEADERBOARD_SPECS[livePath];
  const origin = new URL(requestUrl).origin;
  return new Request(new URL(spec.cachePath, origin), { method: "GET" });
}

/**
 * @param {Cache | { put: Function, match: Function } | null | undefined} override
 * @returns {Cache | { put: Function, match: Function } | null}
 */
export function runtimeCache(override) {
  if (override) {
    return override;
  }
  const cachesObj = globalThis.caches;
  if (cachesObj && cachesObj.default) {
    return cachesObj.default;
  }
  return null;
}

/**
 * @param {Response} upstream
 * @returns {Promise<object | null>}
 */
async function readJsonPayload(upstream) {
  const text = await upstream.clone().text();
  try {
    const payload = JSON.parse(text);
    if (!isLeaderboardPayload(payload)) {
      return null;
    }
    return payload;
  } catch (_err) {
    return null;
  }
}

/**
 * Store a successful live leaderboard response for Sleeping reads.
 *
 * @param {string} requestUrl
 * @param {string} livePath
 * @param {Response} upstream
 * @param {Cache | { put: Function } | null} [cache]
 * @returns {Promise<void>}
 */
export async function rememberLeaderboardResponse(
  requestUrl,
  livePath,
  upstream,
  cache
) {
  if (!upstream || !upstream.ok || !isLeaderboardLivePath(livePath)) {
    return;
  }
  const store = runtimeCache(cache);
  if (!store) {
    return;
  }
  const payload = await readJsonPayload(upstream);
  if (!payload) {
    return;
  }
  const stored = new Response(JSON.stringify(payload), {
    status: 200,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": CACHE_STORE_CONTROL,
      "x-cvh-leaderboard": "origin",
    },
  });
  try {
    await store.put(leaderboardCacheRequest(requestUrl, livePath), stored);
  } catch (_err) {
    // Cache API is best-effort; git /data JSON remains the last fallback.
  }
}

/**
 * @param {string} requestUrl
 * @param {string} livePath
 * @param {Cache | { match: Function } | null} [cache]
 * @returns {Promise<object | null>}
 */
export async function readCachedLeaderboardPayload(requestUrl, livePath, cache) {
  const store = runtimeCache(cache);
  if (!store) {
    return null;
  }
  try {
    const hit = await store.match(leaderboardCacheRequest(requestUrl, livePath));
    if (!hit || !hit.ok) {
      return null;
    }
    return readJsonPayload(hit);
  } catch (_err) {
    return null;
  }
}

/**
 * @param {{ fetch: (request: Request) => Promise<Response> } | undefined} assets
 * @param {string} requestUrl
 * @param {string} assetPath
 * @returns {Promise<object | null>}
 */
export async function readAssetLeaderboardPayload(assets, requestUrl, assetPath) {
  if (!assets || typeof assets.fetch !== "function") {
    return null;
  }
  try {
    const res = await assets.fetch(
      new Request(new URL(assetPath, requestUrl), {
        method: "GET",
        headers: { accept: "application/json" },
        redirect: "manual",
      })
    );
    if (!res.ok) {
      return null;
    }
    return readJsonPayload(res);
  } catch (_err) {
    return null;
  }
}

/**
 * @param {object} payload
 * @param {string} source
 * @returns {Response}
 */
export function snapshotResponse(payload, source) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: {
      ...JSON_HEADERS,
      "x-cvh-leaderboard": source,
    },
  });
}

/**
 * Serve last-known-good leaderboard JSON without touching GAME_ORIGIN.
 *
 * @param {{
 *   requestUrl: string,
 *   livePath: string,
 *   assets?: { fetch: (request: Request) => Promise<Response> },
 *   cache?: Cache | { put: Function, match: Function } | null,
 * }} opts
 * @returns {Promise<Response>}
 */
export async function serveLeaderboardSnapshot(opts) {
  const spec = LEADERBOARD_SPECS[opts.livePath];
  if (!spec) {
    return new Response(JSON.stringify({ ok: false, error: "Not Found" }), {
      status: 404,
      headers: JSON_HEADERS,
    });
  }

  const cached = await readCachedLeaderboardPayload(
    opts.requestUrl,
    opts.livePath,
    opts.cache
  );
  const asset = await readAssetLeaderboardPayload(
    opts.assets,
    opts.requestUrl,
    spec.assetPath
  );
  const chosen = preferNewerSnapshot(cached, asset);
  if (chosen) {
    const source =
      cached && chosen === cached ? "cache" : asset && chosen === asset ? "static" : "cache";
    return snapshotResponse(chosen, source);
  }
  return new Response(JSON.stringify({ ok: false, error: "No leaderboard snapshot" }), {
    status: 404,
    headers: JSON_HEADERS,
  });
}

/**
 * @param {{ waitUntil?: (p: Promise<unknown>) => void }} context
 * @param {Promise<unknown>} work
 */
export function scheduleBackground(context, work) {
  if (context && typeof context.waitUntil === "function") {
    context.waitUntil(work);
    return;
  }
  Promise.resolve(work).catch(() => {});
}
