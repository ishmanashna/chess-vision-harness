import { normalizeOrigin } from "../_proxy.js";

/** Tunnel wake can be slow; 3s probes stay Sleeping after go-online. */
const HEALTH_TIMEOUT_MS = 10000;
const NO_STORE_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store, no-cache, must-revalidate, max-age=0",
  "cdn-cache-control": "no-store",
};

/**
 * GET /api/edge-health — probes GAME_ORIGIN/health with a short timeout.
 */
export async function onRequest({ env }) {
  const origin = normalizeOrigin(env.GAME_ORIGIN);

  if (!origin) {
    return Response.json(
      {
        status: "offline",
        online: false,
        origin: false,
        message: "GAME_ORIGIN is not configured on this Pages project.",
      },
      { headers: NO_STORE_HEADERS }
    );
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);

  try {
    const res = await fetch(`${origin}/health`, {
      method: "GET",
      headers: { accept: "application/json" },
      signal: controller.signal,
      // Don't reuse a stale origin /health from CF cache for this probe.
      cf: { cacheTtl: 0, cacheEverything: false },
    });

    if (!res.ok) {
      throw new Error(`health status ${res.status}`);
    }

    const body = await res.json().catch(() => ({}));
    const healthy = body && (body.ok === true || body.status === "up");

    if (!healthy) {
      throw new Error("health payload not ok");
    }

    return Response.json(
      {
        status: "online",
        online: true,
        origin: true,
        message: "Game server is reachable.",
      },
      { headers: NO_STORE_HEADERS }
    );
  } catch (_err) {
    return Response.json(
      {
        status: "offline",
        online: false,
        origin: true,
        message: "Game server is unreachable.",
      },
      { headers: NO_STORE_HEADERS }
    );
  } finally {
    clearTimeout(timer);
  }
}
