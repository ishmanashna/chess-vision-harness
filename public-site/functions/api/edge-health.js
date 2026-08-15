import { normalizeOrigin } from "../_proxy.js";

/** Keep probes snappy — slow tunnels should fail fast, not block navigation. */
const HEALTH_TIMEOUT_MS = 3000;
/** Edge CDN cache for successful Online answers (seconds). Offline stays uncached. */
const ONLINE_CACHE_S_MAXAGE = 12;

/**
 * GET /api/edge-health — probes GAME_ORIGIN/health with a short timeout.
 */
export async function onRequest({ env }) {
  const origin = normalizeOrigin(env.GAME_ORIGIN);
  const baseHeaders = {
    "content-type": "application/json; charset=utf-8",
  };

  if (!origin) {
    return Response.json(
      {
        status: "offline",
        online: false,
        origin: false,
        message: "GAME_ORIGIN is not configured on this Pages project.",
      },
      {
        headers: {
          ...baseHeaders,
          "cache-control": "no-store",
        },
      }
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
      {
        headers: {
          ...baseHeaders,
          // Short edge cache so tab navigations reuse the last Online without a full tunnel hop.
          "cache-control": `public, max-age=0, s-maxage=${ONLINE_CACHE_S_MAXAGE}`,
        },
      }
    );
  } catch (_err) {
    return Response.json(
      {
        status: "offline",
        online: false,
        origin: true,
        message: "Game server is unreachable.",
      },
      {
        headers: {
          ...baseHeaders,
          "cache-control": "no-store",
        },
      }
    );
  } finally {
    clearTimeout(timer);
  }
}
