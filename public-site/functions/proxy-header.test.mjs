import assert from "node:assert/strict";
import test from "node:test";

import { buildProxyRequestHeaders, clientIpFromRequest } from "./_proxy.js";
import {
  fetchWatchShellHtml,
  injectShellEntityId,
} from "./_watch_shell.js";

test("clientIpFromRequest prefers CF-Connecting-IP", () => {
  const request = new Request("https://chessvisionharness.pages.dev/api/v1/games", {
    headers: {
      "cf-connecting-ip": "203.0.113.10",
      "x-forwarded-for": "10.0.0.1",
    },
  });
  assert.equal(clientIpFromRequest(request), "203.0.113.10");
});

test("clientIpFromRequest falls back to first X-Forwarded-For hop", () => {
  const request = new Request("https://chessvisionharness.pages.dev/api/v1/games", {
    headers: {
      "x-forwarded-for": "198.51.100.4, 10.0.0.1",
    },
  });
  assert.equal(clientIpFromRequest(request), "198.51.100.4");
});

test("buildProxyRequestHeaders forwards visitor IP and strips spoofable headers", () => {
  const request = new Request("https://chessvisionharness.pages.dev/api/v1/games", {
    headers: {
      host: "chessvisionharness.pages.dev",
      "cf-connecting-ip": "203.0.113.10",
      "x-forwarded-for": "10.0.0.1",
      "x-real-ip": "10.0.0.2",
      authorization: "Bearer test-key",
    },
  });
  const headers = buildProxyRequestHeaders(request);
  assert.equal(headers.get("x-forwarded-for"), "203.0.113.10");
  assert.equal(headers.get("cf-connecting-ip"), null);
  assert.equal(headers.get("x-real-ip"), null);
  assert.equal(headers.get("host"), null);
  assert.equal(headers.get("authorization"), "Bearer test-key");
});

test("fetchWatchShellHtml follows ASSETS index redirect without leaking it", async () => {
  const calls = [];
  const assets = {
    async fetch(request) {
      const url = new URL(request.url);
      calls.push({ url: url.pathname, redirect: request.redirect });
      if (url.pathname === "/g/index.html") {
        return new Response(null, {
          status: 308,
          headers: { Location: "/g/" },
        });
      }
      if (url.pathname === "/g/" || url.pathname === "/g") {
        return new Response("<!doctype html><title>shell</title>", {
          status: 200,
          headers: { "content-type": "text/html" },
        });
      }
      return new Response("missing", { status: 404 });
    },
  };
  const request = new Request(
    "https://chessvisionharness.pages.dev/g/game-abc123"
  );
  const res = await fetchWatchShellHtml(assets, request, "/g/index.html");
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("content-type"), "text/html; charset=utf-8");
  assert.equal(await res.text(), "<!doctype html><title>shell</title>");
  assert.deepEqual(
    calls.map((c) => c.url),
    ["/g/index.html", "/g/"]
  );
  assert.equal(calls[0].redirect, "manual");
});

test("fetchWatchShellHtml follows puzzle shell redirect without leaking it", async () => {
  const calls = [];
  const assets = {
    async fetch(request) {
      const url = new URL(request.url);
      calls.push({ url: url.pathname, redirect: request.redirect });
      if (url.pathname === "/p/index.html") {
        return new Response(null, {
          status: 308,
          headers: { Location: "/p/" },
        });
      }
      if (url.pathname === "/p/" || url.pathname === "/p") {
        return new Response(
          "<!doctype html><body class=\"puzzle-view\"><title>puzzle shell</title></body>",
          {
            status: 200,
            headers: { "content-type": "text/html" },
          }
        );
      }
      return new Response("missing", { status: 404 });
    },
  };
  const request = new Request(
    "https://chessvisionharness.pages.dev/p/pz-abc123def456"
  );
  const res = await fetchWatchShellHtml(assets, request, "/p/index.html");
  assert.equal(res.status, 200);
  assert.equal(res.headers.get("content-type"), "text/html; charset=utf-8");
  const body = await res.text();
  assert.ok(body.includes("puzzle shell"));
  assert.match(body, /data-attempt-id="pz-abc123def456"/);
  assert.deepEqual(
    calls.map((c) => c.url),
    ["/p/index.html", "/p/"]
  );
  assert.equal(calls[0].redirect, "manual");
});

test("fetchWatchShellHtml injects data-attempt-id from browser path", async () => {
  const assets = {
    async fetch() {
      return new Response("<!doctype html><body class=\"puzzle-view\"></body>", {
        status: 200,
        headers: { "content-type": "text/html" },
      });
    },
  };
  const request = new Request(
    "https://chessvisionharness.pages.dev/i/id-xyz789"
  );
  const res = await fetchWatchShellHtml(assets, request, "/i/index.html");
  assert.equal(res.status, 200);
  assert.match(await res.text(), /data-attempt-id="id-xyz789"/);
});

test("injectShellEntityId adds data-game-id for game watch paths", () => {
  const html = "<!doctype html><body></body>";
  const out = injectShellEntityId(html, "/g/game-abc123");
  assert.match(out, /data-game-id="game-abc123"/);
});
