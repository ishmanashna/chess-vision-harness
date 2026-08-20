import {
  isCalibrationPath,
  isPuzzleSetPath,
  isWatchShellHtml,
  normalizeOrigin,
  proxyToOrigin,
  shouldProxyToOrigin,
  watchShellAssetPath,
} from "./_proxy.js";
import { fetchWatchShellHtml } from "./_watch_shell.js";

/**
 * @param {URL} url
 * @returns {Response | null}
 */
function launcherRedirect(url) {
  const pathname = url.pathname;
  if (pathname === "/create" || pathname === "/create/") {
    const mode = url.searchParams.get("mode");
    if (mode === "human" || mode === "avh") {
      return Response.redirect(new URL("/launch/?flow=playground", url.origin), 301);
    }
    if (mode === "avaa") {
      return Response.redirect(new URL("/launch/?flow=avaa", url.origin), 301);
    }
    return Response.redirect(new URL("/launch/?flow=engine", url.origin), 301);
  }
  if (pathname === "/human" || pathname === "/human/") {
    return Response.redirect(new URL("/launch/?flow=playground", url.origin), 301);
  }
  if (pathname === "/puzzles" || pathname === "/puzzles/") {
    return Response.redirect(new URL("/launch/?flow=puzzles", url.origin), 301);
  }
  if (pathname === "/identify" || pathname === "/identify/") {
    return Response.redirect(new URL("/launch/?flow=identify", url.origin), 301);
  }
  if (pathname === "/lobby" || pathname === "/lobby/") {
    return Response.redirect(new URL("/launch/?flow=avaa", url.origin), 301);
  }
  return null;
}

/**
 * Pages middleware: block calibration on the public edge; proxy live paths to GAME_ORIGIN.
 * Static assets and other routes fall through to Pages static hosting.
 */
export async function onRequest(context) {
  const { request, env, next } = context;
  const url = new URL(request.url);
  const pathname = url.pathname;

  const redirect = launcherRedirect(url);
  if (redirect) return redirect;

  if (isCalibrationPath(pathname) || isPuzzleSetPath(pathname)) {
    return new Response(JSON.stringify({ ok: false, error: "Not Found" }), {
      status: 404,
      headers: { "content-type": "application/json; charset=utf-8" },
    });
  }

  if (
    pathname.startsWith("/api/") &&
    pathname !== "/api/edge-health" &&
    !shouldProxyToOrigin(pathname)
  ) {
    return new Response(JSON.stringify({ ok: false, error: "Not Found" }), {
      status: 404,
      headers: { "content-type": "application/json; charset=utf-8" },
    });
  }

  const origin = normalizeOrigin(env.GAME_ORIGIN);

  if (isWatchShellHtml(pathname)) {
    const asset = watchShellAssetPath(pathname);
    if (asset && env.ASSETS) {
      // Do not return ASSETS redirects: /g/index.html → /g/ strips the game id.
      return fetchWatchShellHtml(env.ASSETS, request, asset);
    }
    return next();
  }

  if (origin && shouldProxyToOrigin(pathname)) {
    return proxyToOrigin(request, origin);
  }

  return next();
}
