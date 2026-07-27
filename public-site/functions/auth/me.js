import { jsonResponse, oauthConfigured, readSession } from "./_session.js";

/** GET /auth/me — current cosmetic session (no API enforcement). */
export async function onRequestGet({ request, env }) {
  const configured = oauthConfigured(env);
  if (!configured) {
    return jsonResponse({ logged_in: false, oauth_configured: false });
  }
  const session = await readSession(request, env);
  if (!session) {
    return jsonResponse({ logged_in: false, oauth_configured: true });
  }
  return jsonResponse({
    logged_in: true,
    oauth_configured: true,
    google_id: session.google_id,
    email: session.email,
    name: session.name,
    picture: session.picture,
  });
}
