/**
 * Watch/play shell HTML loading for Cloudflare Pages ASSETS.
 * Kept separate from `_proxy.js` so Node can unit-test without the Wrangler-only JSON import.
 */

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
  return new Response(res.body, {
    status: 200,
    statusText: "OK",
    headers,
  });
}
