import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const flush = () => new Promise((resolve) => setImmediate(resolve));

function requests(fetch) {
  const context = { window: { CVH: {} }, fetch, AbortController, Map, Promise, setTimeout, clearTimeout };
  vm.createContext(context);
  vm.runInContext(source("ops-requests.js"), context);
  return context.window.CVH.opsRequest;
}

test("overlapping requests deduplicate until the response body finishes", async () => {
  let calls = 0, resolveBody;
  const body = new Promise((resolve) => { resolveBody = resolve; });
  const request = requests(async () => { calls++; return { ok: true, json: () => body }; });
  const first = request("snapshot", "/snapshot");
  assert.equal(request("snapshot", "/snapshot"), first);
  await flush();
  assert.equal(calls, 1);
  resolveBody({ ok: true });
  assert.deepEqual(await first, { ok: true });
  await request("snapshot", "/snapshot");
  assert.equal(calls, 2);
});

test("timeout aborts and releases a stuck request, including a stuck body", async () => {
  let signal;
  const request = requests(async (_url, options) => {
    signal = options.signal;
    return { ok: true, json: () => new Promise(() => {}) };
  });
  await assert.rejects(request("audience", "/audience", 15), /timed out/);
  assert.equal(signal.aborted, true);
  await assert.rejects(request("audience", "/audience", 15), /timed out/);
});

test("failed sections do not reject independent snapshot requests", async () => {
  const request = requests(async (url) => ({ ok: url !== "/audience", status: 503, json: async () => ({ health: "up" }) }));
  const failed = assert.rejects(request("audience", "/audience"), /HTTP 503/);
  assert.deepEqual(await request("snapshot", "/snapshot"), { health: "up" });
  await failed;
});

test("operational POST requests are bounded and preserve their method", async () => {
  let options;
  const request = requests(async (_url, supplied) => {
    options = supplied;
    return { ok: true, json: async () => ({ status: "running" }) };
  });
  await request("start", "/go-online", 100, { method: "POST" });
  assert.equal(options.method, "POST");
  assert.equal(options.cache, "no-store");
  assert.ok(options.signal);
});

test("Ops lazily loads hidden sections and updates Overview during a hung audience request", async () => {
  const calls = [], listeners = {}, buttons = {}, fields = {};
  let tick, experimentRefreshes = 0;
  const ids = ["overview", "traffic", "prompt-test", "inbox", "machine"];
  const node = (id) => ({ hidden: id !== "overview", classList: { toggle() {} },
    getAttribute: () => id, setAttribute() {}, addEventListener(_name, cb) { this.click = cb; } });
  ids.forEach((id) => { buttons[id] = node(id); });
  const sections = ids.map(node);
  ["[data-ops-updated]", "[data-ops-error]", "[data-audience-status]", "[data-inbox-status]"].forEach((key) => { fields[key] = {}; });
  const panel = { querySelector: (sel) => fields[sel] || null,
    querySelectorAll: (sel) => sel === "[data-ops-tab]" ? Object.values(buttons) : sections };
  const context = {
    window: { CVH: { refreshOpsExperiments() { experimentRefreshes++; } } },
    document: { hidden: false, querySelector: () => panel, addEventListener: (name, cb) => { listeners[name] = cb; } },
    fetch: async (url) => {
      calls.push(url);
      if (url === "/api/ops/audience") return new Promise(() => {});
      return { ok: true, json: async () => url === "/api/ops/go-online" ? { status: "idle" }
        : { generated_at: "2026-10-13T12:00:00Z", messages: [], health: { ok: true } } };
    },
    AbortController, Map, Promise, clearTimeout,
    setTimeout: (cb, ms) => setTimeout(cb, ms).unref(),
    setInterval: (cb) => { tick = cb; }, clearInterval() {},
  };
  vm.createContext(context);
  vm.runInContext(source("ops-requests.js"), context);
  vm.runInContext(source("ops.js"), context);
  listeners.DOMContentLoaded();
  await flush();
  assert.ok(calls.includes("/api/ops/snapshot"));
  assert.ok(!calls.includes("/api/ops/audience") && !calls.includes("/api/contact/inbox"));
  assert.equal(experimentRefreshes, 0);
  buttons.traffic.click();
  await flush();
  assert.equal(calls.filter((url) => url === "/api/ops/audience").length, 1);
  fields["[data-ops-updated]"].textContent = "sentinel";
  tick(); await flush();
  assert.match(fields["[data-ops-updated]"].textContent, /Updated/);
  assert.equal(calls.filter((url) => url === "/api/ops/audience").length, 1);
  buttons["prompt-test"].click(); await flush();
  assert.equal(experimentRefreshes, 1);
  buttons.inbox.click(); await flush();
  assert.ok(calls.includes("/api/contact/inbox"));
  assert.ok(!calls.includes("/api/ops/health"));
  buttons.machine.click(); await flush();
  assert.ok(calls.includes("/api/ops/health"));
  assert.ok(calls.filter((url) => url === "/api/ops/go-online").length > 1);
  const before = calls.length;
  context.document.hidden = true; tick(); await flush();
  assert.equal(calls.length, before);
});
