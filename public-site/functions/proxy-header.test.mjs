import assert from "node:assert/strict";
import test from "node:test";

import { buildProxyRequestHeaders, clientIpFromRequest } from "./_proxy.js";

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
