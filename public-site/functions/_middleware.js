import {
  isCalibrationPath,
  normalizeOrigin,
  proxyToOrigin,
  shouldProxyPath,
} from "./_proxy.js";

/**
 * @param {URL} url
 * @returns {Response | null}
 */
function humanCreateRedirect(url) {
  const pathname = url.pathname;
  if (pathname !== "/create" && pathname !== "/create/") return null;
  const mode = url.searchParams.get("mode");
  if (mode === "human" || mode === "avh") {
    return Response.redirect(new URL("/human/", url.origin), 301);
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

  const humanRedirect = humanCreateRedirect(url);
  if (humanRedirect) return humanRedirect;

  if (isCalibrationPath(pathname)) {
    return new Response("Not Found", {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }

  const origin = normalizeOrigin(env.GAME_ORIGIN);
  if (origin && shouldProxyPath(pathname)) {
    return proxyToOrigin(request, origin);
  }

  return next();
}
