import {
  STATE_COOKIE,
  STATE_MAX_AGE,
  oauthConfigured,
  setCookie,
  signPayload,
} from "./_session.js";

/** GET /auth/google — start Google OAuth. */
export async function onRequestGet({ request, env }) {
  if (!oauthConfigured(env)) {
    return new Response("Google sign-in is not configured on this site.", {
      status: 503,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }

  const url = new URL(request.url);
  const redirectUri = `${url.origin}/auth/callback`;
  const state = crypto.randomUUID();
  const stateToken = await signPayload(
    { state, exp: Date.now() + STATE_MAX_AGE * 1000 },
    env.AUTH_SESSION_SECRET
  );

  const authUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  authUrl.searchParams.set("client_id", env.GOOGLE_CLIENT_ID);
  authUrl.searchParams.set("redirect_uri", redirectUri);
  authUrl.searchParams.set("response_type", "code");
  authUrl.searchParams.set("scope", "openid email profile");
  authUrl.searchParams.set("state", state);
  authUrl.searchParams.set("access_type", "online");
  authUrl.searchParams.set("prompt", "select_account");

  return new Response(null, {
    status: 302,
    headers: {
      Location: authUrl.toString(),
      "Set-Cookie": setCookie(STATE_COOKIE, stateToken, STATE_MAX_AGE, request),
    },
  });
}
