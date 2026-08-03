/**
 * Shared origin proxy helpers for Pages Functions.
 * GAME_ORIGIN must be set in the Cloudflare Pages dashboard (no trailing slash).
 */

const PROXY_TIMEOUT_MS = 25000;

/** @param {string | undefined} origin */
export function normalizeOrigin(origin) {
  return (origin || "").trim().replace(/\/+$/, "");
}

/**
 * @param {string} pathname
 * @returns {boolean}
 */
export function shouldProxyPath(pathname) {
  return (
    pathname.startsWith("/api/v1/") ||
    pathname === "/api/v1" ||
    pathname.startsWith("/api/games") ||
    pathname.startsWith("/api/play") ||
    pathname === "/api/contact" ||
    pathname === "/api/contact/" ||
    pathname === "/api/leaderboard/live" ||
    pathname.startsWith("/g/") ||
    pathname.startsWith("/play/")
  );
}

/**
 * @param {string} pathname
 * @returns {boolean}
 */
export function isCalibrationPath(pathname) {
  return pathname === "/calibration" || pathname.startsWith("/calibration/");
}

/**
 * @param {Request} request
 * @param {string} origin
 * @returns {Promise<Response>}
 */
export async function proxyToOrigin(request, origin) {
  const base = normalizeOrigin(origin);
  if (!base) {
    return new Response(JSON.stringify({ ok: false, error: "GAME_ORIGIN not configured" }), {
      status: 503,
      headers: { "content-type": "application/json; charset=utf-8" },
    });
  }

  const url = new URL(request.url);
  const target = base + url.pathname + url.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("x-forwarded-for");
  headers.delete("x-real-ip");
  headers.delete("cf-connecting-ip");

  /** @type {RequestInit} */
  const init = {
    method: request.method,
    headers,
    redirect: "manual",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROXY_TIMEOUT_MS);

  try {
    const upstream = await fetch(target, { ...init, signal: controller.signal });
    const outHeaders = new Headers(upstream.headers);
    outHeaders.set("cache-control", "no-store");
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: outHeaders,
    });
  } catch (_err) {
    return new Response(JSON.stringify({ ok: false, error: "Origin unreachable" }), {
      status: 502,
      headers: { "content-type": "application/json; charset=utf-8" },
    });
  } finally {
    clearTimeout(timer);
  }
}
