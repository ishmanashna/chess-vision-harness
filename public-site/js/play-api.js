/** Human play API client (/api/play). */

export function readPlayToken() {
  try {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("token");
    if (q && q.trim()) return q.trim();
  } catch (_e) {
    /* ignore */
  }
  return "";
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
