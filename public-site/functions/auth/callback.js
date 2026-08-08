import {
  STATE_COOKIE,
  clearCookie,
  oauthConfigured,
  parseCookies,
  buildSessionCookie,
  verifySigned,
} from "./_session.js";

/** GET /auth/callback — finish Google OAuth and set session cookie. */
export async function onRequestGet({ request, env }) {
  if (!oauthConfigured(env)) {
    return new Response("Google sign-in is not configured on this site.", {
      status: 503,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }

  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const cookies = parseCookies(request);
  const stateCookie = cookies[STATE_COOKIE];
  const stateData = stateCookie
    ? await verifySigned(stateCookie, env.AUTH_SESSION_SECRET)
    : null;

  if (!code || !state || !stateData || stateData.state !== state) {
    return new Response("Invalid sign-in state. Try again.", {
      status: 400,
      headers: {
        "content-type": "text/plain; charset=utf-8",
        "Set-Cookie": clearCookie(STATE_COOKIE, request),
      },
    });
  }

  const redirectUri = `${url.origin}/auth/callback`;
  const body = new URLSearchParams({
    code,
    client_id: env.GOOGLE_CLIENT_ID,
    client_secret: env.GOOGLE_CLIENT_SECRET,
    redirect_uri: redirectUri,
    grant_type: "authorization_code",
  });

  const tokenRes = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });

  if (!tokenRes.ok) {
    return new Response("Google token exchange failed.", { status: 502 });
  }

  const tokenBody = await tokenRes.json();
  const accessToken = tokenBody.access_token;
  if (!accessToken) {
    return new Response("Google did not return an access token.", { status: 502 });
  }

  const userRes = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
    headers: { authorization: `Bearer ${accessToken}` },
  });

  if (!userRes.ok) {
    return new Response("Failed to fetch Google profile.", { status: 502 });
  }

  const user = await userRes.json();
  if (!user.sub || !user.email) {
    return new Response("Google profile missing email.", { status: 502 });
  }

  const sessionCookie = await buildSessionCookie(
    {
      google_id: String(user.sub),
      email: user.email,
      name: user.name || user.email,
      picture: user.picture || "",
    },
    env,
    request
  );

  const headers = new Headers({ Location: "/launch/" });
  headers.append("Set-Cookie", sessionCookie);
  headers.append("Set-Cookie", clearCookie(STATE_COOKIE, request));
  return new Response(null, { status: 302, headers });
}
