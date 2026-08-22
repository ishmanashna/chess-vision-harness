import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";

const commonPath = path.join(import.meta.dirname, "common.js");
const commonSrc = fs.readFileSync(commonPath, "utf8");

function loadUmamiHelper() {
  const context = {
    window: {
      location: { hostname: "chessvisionharness.pages.dev", pathname: "/" },
      CVH: {},
      addEventListener: () => {},
    },
    document: {
      documentElement: { getAttribute: () => "light", setAttribute: () => {} },
      getElementById: () => null,
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener: () => {},
      head: { appendChild: () => {} },
      body: { appendChild: () => {} },
    },
    localStorage: { getItem: () => null, setItem: () => {} },
    matchMedia: () => ({ matches: false }),
    Promise: Promise,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    fetch: () => Promise.reject(new Error("fetch not stubbed")),
  };
  vm.createContext(context);
  vm.runInContext(commonSrc, context);
  return context.window.CVH.shouldLoadUmamiTracker;
}

test("shouldLoadUmamiTracker loads on Pages host with website id", () => {
  const shouldLoad = loadUmamiHelper();
  assert.equal(
    shouldLoad("chessvisionharness.pages.dev", "website-id", "chessvisionharness.pages.dev"),
    true
  );
});

test("shouldLoadUmamiTracker skips loopback hosts", () => {
  const shouldLoad = loadUmamiHelper();
  assert.equal(shouldLoad("127.0.0.1", "website-id", "chessvisionharness.pages.dev"), false);
  assert.equal(shouldLoad("localhost", "website-id", "chessvisionharness.pages.dev"), false);
});

test("shouldLoadUmamiTracker skips without website id", () => {
  const shouldLoad = loadUmamiHelper();
  assert.equal(shouldLoad("chessvisionharness.pages.dev", "", "chessvisionharness.pages.dev"), false);
});

test("shouldLoadUmamiTracker skips non-Pages hostnames", () => {
  const shouldLoad = loadUmamiHelper();
  assert.equal(
    shouldLoad("random.trycloudflare.com", "website-id", "chessvisionharness.pages.dev"),
    false
  );
});
