/**
 * Watch/play shell HTML loading for Cloudflare Pages ASSETS.
 * Kept separate from `_proxy.js` so Node can unit-test without the Wrangler-only JSON import.
 */

/**
 * @param {string} pathname Browser request pathname (e.g. `/p/pz-abc`).
 * @returns {{ attr: string, id: string } | null}
 */
export function shellEntityFromPath(pathname) {
  const segments = pathname.replace(/\/+$/, "").split("/").filter(Boolean);
  const kind = segments[0] || "";
  const id = (segments[1] || "").trim();
  if (!id || id === "index.html") {
    return null;
  }
  if (kind === "p" || kind === "i") {
    return { attr: "data-attempt-id", id };
  }
  if (kind === "g" || kind === "play") {
    return { attr: "data-game-id", id };
  }
  return null;
}

/**
 * Inject entity id onto the shell `<body>` so watch JS does not depend on the URL alone.
 *
 * @param {string} html
 * @param {string} pathname
 * @returns {string}
 */
export function injectShellEntityId(html, pathname) {
  const entity = shellEntityFromPath(pathname);
  if (!entity) {
    return html;
  }
  const safe = entity.id
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return html.replace(/<body(\s[^>]*)?>/i, (match, attrs) => {
    if (match.includes(entity.attr)) {
      return match;
    }
    const a = attrs || "";
    return `<body${a} ${entity.attr}="${safe}">`;
  });
}

/**
 * Load watch/play shell HTML from Pages ASSETS without leaking Cloudflare's
 * directory-index redirect (`/g/index.html` -> 308 `/g/`) to the browser.
 * That redirect strips `/g/{id}` (and `/p|/i|/play`) and leaves an empty watch page.
 *
 * @param {{ fetch: (request: Request) => Promise<Response> }} assets
 * @param {Request} request Original browser request (URL kept; only used as base).
 * @param {string} assetPath e.g. `/g/index.html`
 * @returns {Promise<Response>}
 */
export async function fetchWatchShellHtml(assets, request, assetPath) {
  const shellUrl = new URL(assetPath, request.url);
  /** @type {RequestInit} */
  const getInit = {
    method: "GET",
    headers: { accept: "text/html" },
    redirect: "manual",
  };
  let res = await assets.fetch(new Request(shellUrl.toString(), getInit));
  if (res.status >= 300 && res.status < 400) {
    const loc = res.headers.get("Location");
    if (!loc) {
      return res;
    }
    const nextUrl = new URL(loc, shellUrl);
    res = await assets.fetch(
      new Request(nextUrl.toString(), {
        method: "GET",
        headers: { accept: "text/html" },
      })
    );
  }
  if (!res.ok) {
    return res;
  }
  const headers = new Headers(res.headers);
  const ct = headers.get("content-type") || "";
  if (!ct || ct.startsWith("text/html")) {
    headers.set("content-type", "text/html; charset=utf-8");
  }
  const html = injectShellEntityId(
    await res.text(),
    new URL(request.url).pathname
  );
  return new Response(html, {
    status: 200,
    statusText: "OK",
    headers,
  });
}
