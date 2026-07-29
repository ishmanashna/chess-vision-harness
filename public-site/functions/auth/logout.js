import { clearCookie, SESSION_COOKIE } from "./_session.js";
import { safeLogoutPath } from "./_redirect.js";

/** GET /auth/logout — clear session cookie and return home. */
export async function onRequestGet({ request }) {
  const next = new URL(request.url).searchParams.get("next") || "/";
  const target = safeLogoutPath(next);
  return new Response(null, {
    status: 302,
    headers: {
      Location: target,
      "Set-Cookie": clearCookie(SESSION_COOKIE, request),
    },
  });
}
