import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";

const jsDir = import.meta.dirname;
const commonPath = path.join(jsDir, "common.js");
const edgeHealthPath = path.join(jsDir, "..", "functions", "api", "edge-health.js");
const commonSrc = fs.readFileSync(commonPath, "utf8");
const edgeHealthSrc = fs.readFileSync(edgeHealthPath, "utf8");

function parseEdgeHealthTimeoutMs() {
  const match = edgeHealthSrc.match(/HEALTH_TIMEOUT_MS\s*=\s*(\d+)/);
  assert.ok(match, "HEALTH_TIMEOUT_MS not found in edge-health.js");
  return Number(match[1]);
}

function loadHealthHelpers() {
  const context = {
    window: {
      location: { hostname: "chessvisionharness.pages.dev", pathname: "/" },
      CVH: {},
      addEventListener: () => {},
    },
    document: {
      documentElement: { getAttribute: () => "light", setAttribute: () => {} },
      hidden: false,
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener: () => {},
      head: { appendChild: () => {} },
      body: { appendChild: () => {} },
    },
    sessionStorage: { getItem: () => null, setItem: () => {} },
    localStorage: { getItem: () => null, setItem: () => {} },
    matchMedia: () => ({ matches: false }),
    Promise: Promise,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    fetch: () => Promise.reject(new Error("fetch not stubbed")),
  };
  vm.createContext(context);
  vm.runInContext(commonSrc, context);
  return context.window.CVH;
}

test("edge-health probe timeout is ~3s class, not 10s", () => {
  const ms = parseEdgeHealthTimeoutMs();
  assert.ok(ms >= 2500 && ms <= 4000, `expected ~3s class, got ${ms}`);
  assert.notEqual(ms, 10000);
});

test("client health fetch timeout is above edge timeout and well under 10s", () => {
  const edgeMs = parseEdgeHealthTimeoutMs();
  const cvh = loadHealthHelpers();
  const clientMs = cvh.HEALTH_FETCH_TIMEOUT_MS;
  assert.ok(clientMs > edgeMs, "client timeout must exceed edge probe");
  assert.ok(clientMs < 10000, "client timeout must stay well under 10s");
});

test("fresh stored health skips force probe on load", () => {
  const cvh = loadHealthHelpers();
  const now = Date.now();
  assert.equal(cvh.shouldForceHealthProbeOnLoad({ online: true, fromStorage: true }), false);
  assert.equal(cvh.isHealthStorageFresh(now - 1000, now), true);
  assert.equal(cvh.shouldForceHealthProbeOnLoad(null), true);
  assert.equal(cvh.isHealthStorageFresh(now - cvh.HEALTH_FRESH_MS - 1, now), false);
});

test("hidden tab pauses Sleeping health poll scheduling", () => {
  const cvh = loadHealthHelpers();
  assert.equal(cvh.shouldPauseHealthPollWhenHidden(true), true);
  assert.equal(cvh.shouldPauseHealthPollWhenHidden(false), false);
});
