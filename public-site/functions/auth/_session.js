/** Shared Google OAuth session helpers for Pages Functions. */

const SESSION_COOKIE = "cvh_session";
const STATE_COOKIE = "cvh_oauth_state";
const SESSION_MAX_AGE = 60 * 60 * 24 * 30; // 30 days
const STATE_MAX_AGE = 600; // 10 minutes

function oauthConfigured(env) {
  return Boolean(
    env &&
      env.GOOGLE_CLIENT_ID &&
      env.GOOGLE_CLIENT_SECRET &&
      env.AUTH_SESSION_SECRET
  );
}

function cookieSecureFlag(request) {
  return new URL(request.url).protocol === "https:" ? "; Secure" : "";
}

function b64urlFromBytes(bytes) {
  let bin = "";
  const arr = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  for (let i = 0; i < arr.length; i++) bin += String.fromCharCode(arr[i]);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlFromString(str) {
  return btoa(unescape(encodeURIComponent(str)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function stringFromB64url(b64url) {
  const padded = b64url.replace(/-/g, "+").replace(/_/g, "/");
  const pad = padded.length % 4 === 0 ? "" : "=".repeat(4 - (padded.length % 4));
  return decodeURIComponent(escape(atob(padded + pad)));
}

async function hmacSha256(secret, message) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  return b64urlFromBytes(sig);
}

async function signPayload(obj, secret) {
  const payload = b64urlFromString(JSON.stringify(obj));
  const sig = await hmacSha256(secret, payload);
  return `${payload}.${sig}`;
}

async function verifySigned(token, secret) {
  if (!token || !secret || typeof token !== "string") return null;
  const parts = token.split(".");
  if (parts.length !== 2) return null;
  const [payload, sig] = parts;
  const expected = await hmacSha256(secret, payload);
  if (sig.length !== expected.length) return null;
  let ok = 0;
  for (let i = 0; i < sig.length; i++) ok |= sig.charCodeAt(i) ^ expected.charCodeAt(i);
  if (ok !== 0) return null;
  try {
    const data = JSON.parse(stringFromB64url(payload));
    if (data.exp && Date.now() > Number(data.exp)) return null;
    return data;
  } catch (_err) {
    return null;
  }
}

function parseCookies(request) {
  const header = request.headers.get("Cookie") || "";
  const out = {};
  header.split(";").forEach((part) => {
    const idx = part.indexOf("=");
    if (idx < 0) return;
    const k = part.slice(0, idx).trim();
    const v = part.slice(idx + 1).trim();
    if (k) out[k] = decodeURIComponent(v);
  });
  return out;
}

function setCookie(name, value, maxAge, request) {
  return (
    `${name}=${encodeURIComponent(value)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${maxAge}` +
    cookieSecureFlag(request)
  );
}

function clearCookie(name, request) {
  return (
    `${name}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0` + cookieSecureFlag(request)
  );
}

async function readSession(request, env) {
  if (!oauthConfigured(env)) return null;
  const cookies = parseCookies(request);
  const raw = cookies[SESSION_COOKIE];
  if (!raw) return null;
  const data = await verifySigned(raw, env.AUTH_SESSION_SECRET);
  if (!data || !data.email) return null;
  return {
    google_id: data.google_id,
    email: data.email,
    name: data.name || "",
    picture: data.picture || "",
  };
}

async function buildSessionCookie(user, env, request) {
  const token = await signPayload(
    {
      google_id: user.google_id,
      email: user.email,
      name: user.name || "",
      picture: user.picture || "",
      exp: Date.now() + SESSION_MAX_AGE * 1000,
    },
    env.AUTH_SESSION_SECRET
  );
  return setCookie(SESSION_COOKIE, token, SESSION_MAX_AGE, request);
}

function jsonResponse(body, init = {}) {
  const headers = new Headers(init.headers || {});
  headers.set("content-type", "application/json; charset=utf-8");
  headers.set("cache-control", "no-store");
  return new Response(JSON.stringify(body), { ...init, headers });
}

export {
  STATE_COOKIE,
  STATE_MAX_AGE,
  oauthConfigured,
  parseCookies,
  setCookie,
  clearCookie,
  readSession,
  buildSessionCookie,
  signPayload,
  verifySigned,
  jsonResponse,
  SESSION_COOKIE,
};
