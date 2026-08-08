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
function launcherRedirect(url) {
  const pathname = url.pathname;
  if (pathname === "/create" || pathname === "/create/") {
    return Response.redirect(new URL("/launch/?flow=engine", url.origin), 301);
  }
  if (pathname === "/human" || pathname === "/human/") {
    return Response.redirect(new URL("/launch/?flow=playground", url.origin), 301);
  }
  if (pathname === "/puzzles" || pathname === "/puzzles/") {
    return Response.redirect(new URL("/launch/?flow=puzzles", url.origin), 301);
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
