/**
 * Shared origin proxy helpers for Pages Functions.
 * GAME_ORIGIN must be set in the Cloudflare Pages dashboard (no trailing slash).
 */

// JS module (not JSON) so Node and Wrangler can import the contract the same way.
import contract from "./proxy-routes.contract.js";

const PROXY_TIMEOUT_MS = 25000;

/** @param {string | undefined} origin */
export function normalizeOrigin(origin) {
  return (origin || "").trim().replace(/\/+$/, "");
}

/**
 * @param {string} pathname
 * @returns {boolean}
 */
export function isWatchShellHtml(pathname) {
  if (/^\/(g|p|i)\/[^/]+\/?$/.test(pathname)) {
    return true;
  }
  return /^\/play\/[^/]+\/?$/.test(pathname);
}

/**
 * Asset subpaths under /g/, /p/, /i/ (board.png, board.txt, answer.png) stay on origin.
 * @param {string} pathname
 * @returns {boolean}
 */
export function isWatchAssetSubpath(pathname) {
  return /^\/(g|p|i)\/[^/]+\/.+/.test(pathname);
}

/**
 * Static shell asset for a watch/play HTML URL.
 * @param {string} pathname
 * @returns {string | null}
 */
export function watchShellAssetPath(pathname) {
  if (pathname.startsWith("/g/")) {
    return "/g/index.html";
  }
  if (pathname.startsWith("/p/")) {
    return "/p/index.html";
  }
  if (pathname.startsWith("/i/")) {
    return "/i/index.html";
  }
  if (pathname.startsWith("/play/")) {
    return "/play/index.html";
  }
  return null;
}

/**
 * Whether a pathname should be proxied to GAME_ORIGIN (API + watch assets only).
 * @param {string} pathname
 * @returns {boolean}
 */
export function shouldProxyToOrigin(pathname) {
  if (isCalibrationPath(pathname)) {
    return false;
  }
  if (isWatchShellHtml(pathname)) {
    return false;
  }
  if (isWatchAssetSubpath(pathname)) {
    return true;
  }
  return shouldProxyPath(pathname);
}

/**
 * @param {string} pathname
 * @returns {boolean}
 */
export function shouldProxyPath(pathname) {
  if (contract.proxy_path_exact.includes(pathname)) {
    return true;
  }
  return contract.proxy_path_prefixes.some((prefix) => pathname.startsWith(prefix));
}

/**
 * @param {string} pathname
 * @returns {boolean}
 */
export function isCalibrationPath(pathname) {
  if (contract.calibration_path_exact.includes(pathname)) {
    return true;
  }
  return contract.calibration_path_prefixes.some((prefix) => pathname.startsWith(prefix));
}

/**
 * @param {string} pathname
 * @returns {boolean}
 */
export function isPuzzleSetPath(pathname) {
  if (contract.puzzle_set_path_exact.includes(pathname)) {
    return true;
  }
  if ((contract.puzzle_set_api_path_prefixes || []).some((prefix) => pathname.startsWith(prefix))) {
    return true;
  }
  return (contract.puzzle_set_path_prefixes || []).some((prefix) =>
    pathname.startsWith(prefix)
  );
}

/**
 * Derive the visitor IP from an edge request (Cloudflare sets CF-Connecting-IP).
 * @param {Request} request
 * @returns {string | null}
 */
export function clientIpFromRequest(request) {
  const cf = request.headers.get("cf-connecting-ip");
  if (cf) {
    const trimmed = cf.trim();
    if (trimmed) {
      return trimmed;
    }
  }
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) {
      return first;
    }
  }
  return null;
}

/**
 * Build upstream headers for proxying to GAME_ORIGIN.
 * Strips hop-by-hop/spoofable identity headers and sets X-Forwarded-For to the visitor IP.
 * @param {Request} request
 * @returns {Headers}
 */
export function buildProxyRequestHeaders(request) {
  const clientIp = clientIpFromRequest(request);
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("x-forwarded-for");
  headers.delete("x-real-ip");
  headers.delete("cf-connecting-ip");
  if (clientIp) {
    headers.set("x-forwarded-for", clientIp);
  }
  return headers;
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

  /** @type {RequestInit} */
  const init = {
    method: request.method,
    headers: buildProxyRequestHeaders(request),
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
