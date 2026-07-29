/** Human play API client (/api/play). */

const SESSION_PREFIX = "cvh-play-token:";

function sessionKey(gameId) {
  return SESSION_PREFIX + String(gameId || "");
}

function gameIdFromPath() {
  const parts = window.location.pathname.replace(/\/+$/, "").split("/");
  return parts[parts.length - 1] || "";
}

function readQueryToken() {
  try {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("token");
    if (q && q.trim()) return q.trim();
  } catch (_e) {
    /* ignore */
  }
  return "";
}

function readSessionToken(gameId) {
  try {
    const stored = sessionStorage.getItem(sessionKey(gameId));
    if (stored && stored.trim()) return stored.trim();
  } catch (_e) {
    /* ignore */
  }
  return "";
}

function readRegistryToken(gameId) {
  try {
    const registry = window.CVH && window.CVH.humanGames;
    const entry = registry && registry.get ? registry.get(gameId) : null;
    if (entry && entry.token) return String(entry.token);
  } catch (_e) {
    /* ignore */
  }
  return "";
}

function persistPlayToken(gameId, token, meta) {
  if (!gameId || !token) return;
  try {
    sessionStorage.setItem(sessionKey(gameId), token);
  } catch (_e) {
    /* ignore */
  }
  try {
    const registry = window.CVH && window.CVH.humanGames;
    if (registry && registry.upsert) {
      registry.upsert({
        gameId,
        token,
        nickname: (meta && meta.nickname) || "",
        agentName: (meta && meta.agentName) || "",
      });
    }
  } catch (_e) {
    /* ignore */
  }
}

function stripTokenFromUrl() {
  try {
    const url = new URL(window.location.href);
    if (!url.searchParams.has("token")) return;
    url.searchParams.delete("token");
    const next = url.pathname + url.search + url.hash;
    window.history.replaceState({}, "", next);
  } catch (_e) {
    /* ignore */
  }
}

/**
 * Resolve play token: ?token= → sessionStorage → localStorage registry;
 * persist to session + registry, then strip ?token= from the URL.
 */
export function readPlayToken(gameId) {
  const id = gameId || gameIdFromPath();
  if (!id) return "";

  const fromQuery = readQueryToken();
  const fromSession = fromQuery ? "" : readSessionToken(id);
  const fromRegistry = fromQuery || fromSession ? "" : readRegistryToken(id);
  const token = fromQuery || fromSession || fromRegistry;
  if (!token) return "";

  persistPlayToken(id, token);
  if (fromQuery) stripTokenFromUrl();
  return token;
}

export function createPlayApi(gameId, token) {
  const base = `/api/play/${encodeURIComponent(gameId)}`;
  const headers = { Authorization: `Bearer ${token}` };

  async function request(path, options) {
    const res = await fetch(base + path, {
      ...options,
      headers: { ...headers, ...(options && options.headers) },
    });
    let body = null;
    try {
      body = await res.json();
    } catch (_e) {
      body = { ok: false, error: "Invalid response" };
    }
    if (!res.ok || body.ok === false) {
      const err = new Error(body.error || `Request failed (${res.status})`);
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return body;
  }

  async function fetchBoardPng() {
    const res = await fetch(`${base}/board.png`, { headers });
    if (!res.ok) {
      throw new Error(`Board PNG failed (${res.status})`);
    }
    return res.blob();
  }

  return {
    fetchPosition: () => request("/position"),
    fetchBoardPng,
    postMove: (uci) =>
      request(`/move/${encodeURIComponent(uci)}`, { method: "POST" }),
    postResign: () => request("/resign", { method: "POST" }),
    postDrawOffer: () => request("/draw/offer", { method: "POST" }),
    postDrawAccept: () => request("/draw/accept", { method: "POST" }),
    postDrawDecline: () => request("/draw/decline", { method: "POST" }),
    fetchChat: (since = 0) =>
      request(`/chat?since=${encodeURIComponent(String(since))}`),
    postChat: (text) =>
      request("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      }),
  };
}

export function uciFromSquares(from, to, promotion) {
  let uci = from + to;
  if (promotion) uci += promotion.toLowerCase();
  return uci;
}

export function normalizeColor(value) {
  const v = String(value || "").toLowerCase();
  return v === "black" ? "black" : "white";
}
