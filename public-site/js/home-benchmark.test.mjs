import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = (name) => fs.readFileSync(new URL(name, import.meta.url), "utf8");
const agents = [
  { id: "missing", name: "Missing", elo: 999, mean_play_rating: null },
  { id: "low", name: "Low", elo: 888, mean_play_rating: -50 },
  { id: "high", name: "High", elo: 777, mean_play_rating: 1200 },
  { id: "zero", name: "Zero", elo: 666, mean_play_rating: 0 },
];

function mount({ home = true, saved, live, rows = agents, inline = true, fail = false } = {}) {
  const storage = new Map(Object.entries(saved || {}));
  const headers = ["name", ...(home ? [] : ["elo"]), "mean_accuracy", "mean_play_rating", "games"]
    .map((key) => ({
      key, attrs: {}, style: {}, classList: { toggle() {} },
      getAttribute() { return key; },
      setAttribute(k, v) { this.attrs[k] = v; },
      addEventListener(_name, cb) { this.click = cb; },
    }));
  const table = { id: "benchmark", querySelectorAll: () => headers };
  const tbody = { innerHTML: "" };
  const meta = { textContent: "" };
  const heading = { appendChild(btn) { this.button = btn; } };
  const root = {
    hasAttribute: (key) => key === "data-leaderboard-full" || (home && key === "data-show-home-benchmark"),
    querySelector: (sel) => ({ table, tbody, "[data-snapshot-meta]": meta, "[data-benchmark-heading]": heading, "[data-benchmark-heading] h2": heading })[sel],
  };
  const ctx = {
    window: {
      CVH: {}, location: { hostname: "localhost", pathname: "/" }, addEventListener() {},
      CVH_INLINE_SNAPSHOT: inline ? { generated_at: "2026-10-13T00:00:00Z", agents: rows } : null,
    },
    document: {
      addEventListener() {}, querySelectorAll: () => [], querySelector: () => null,
      createElement: () => ({ attrs: {}, setAttribute(k, v) { this.attrs[k] = v; },
        addEventListener(_name, cb) { this.click = cb; } }),
    },
    localStorage: { getItem: (k) => storage.get(k) || null, setItem: (k, v) => storage.set(k, v) },
    sessionStorage: { getItem: () => null, setItem() {} },
    AbortController, clearTimeout,
    setTimeout: (cb, ms) => setTimeout(cb, ms).unref(),
    fetch: async (url) => {
      if (fail) throw new Error("offline");
      const payload = url.startsWith("/api/edge-health") ? { online: !!live }
        : { generated_at: "2026-10-13T01:00:00Z", agents: url === "/api/leaderboard/live" ? live : rows };
      return { ok: true, json: async () => payload };
    },
  };
  vm.createContext(ctx);
  vm.runInContext(source("table-sort.js"), ctx);
  vm.runInContext(source("common.js"), ctx);
  ctx.window.CVH.mountLeaderboardTable(root);
  return { tbody, meta, heading, headers, storage };
}

const names = (view) => [...view.tbody.innerHTML.matchAll(/class="agent">([^<]*)/g)].map((m) => m[1]);
const flush = () => new Promise((resolve) => setImmediate(resolve));

test("Home defaults to Performance; eight cells, no Elo or provisional hint", () => {
  const view = mount();
  assert.deepEqual(names(view), ["High", "Zero", "Low", "Missing"]);
  assert.equal((view.tbody.innerHTML.split("</tr>")[0].match(/<td\b/g) || []).length, 8);
  assert.doesNotMatch(view.tbody.innerHTML, /999|888|777|666|Provisional/);
  assert.equal(view.headers.find((h) => h.key === "mean_play_rating").attrs["aria-sort"], "descending");
});

test("migrate Home Elo preference without changing Leaderboards preference", () => {
  const key = "cvh-home-ladder-sort";
  const leaderboardKey = "cvh-leaderboard-agents-sort";
  const view = mount({ saved: {
    [key]: JSON.stringify({ key: "elo", dir: "asc" }),
    [leaderboardKey]: JSON.stringify({ key: "name", dir: "asc" }),
  } });
  assert.deepEqual(JSON.parse(view.storage.get(key)), { key: "mean_play_rating", dir: "desc" });
  assert.deepEqual(JSON.parse(view.storage.get(leaderboardKey)), { key: "name", dir: "asc" });
});

test("preserve valid saved Home sorts and keep missing Performance last ascending", () => {
  const saved = { "cvh-home-ladder-sort": JSON.stringify({ key: "name", dir: "desc" }) };
  assert.deepEqual(names(mount({ saved })), ["Zero", "Missing", "Low", "High"]);
  const view = mount();
  view.headers.find((h) => h.key === "mean_play_rating").click();
  assert.deepEqual(names(view), ["Low", "Zero", "High", "Missing"]);
});

test("expansion control stays in heading, updates count, and collapses again", () => {
  const rows = Array.from({ length: 19 }, (_, i) => ({ id: String(i), name: `Agent ${i}`, mean_play_rating: i }));
  const view = mount({ rows });
  const btn = view.heading.button;
  assert.equal(names(view).length, 15);
  assert.equal(btn.textContent, "Show all (19)");
  assert.equal(btn.attrs["aria-controls"], "benchmark");
  btn.click();
  assert.equal(names(view).length, 19);
  assert.equal(btn.attrs["aria-expanded"], "true");
  btn.click();
  assert.equal(names(view).length, 15);
  assert.equal(btn.attrs["aria-expanded"], "false");
  assert.equal(mount().heading.button.hidden, true);
});

test("live upgrade keeps Performance order and eight-cell Home rendering", async () => {
  const view = mount({ live: [{ id: "new", name: "New live agent", elo: 543, mean_play_rating: 2345 }] });
  await flush();
  assert.deepEqual(names(view), ["New live agent"]);
  assert.match(view.heading.title, /Live ladder/);
  assert.equal(view.meta.textContent, "");
  assert.doesNotMatch(view.tbody.innerHTML, /543/);
});

test("Leaderboards retains Elo and its separate saved sort", () => {
  const view = mount({ home: false, saved: { "cvh-home-ladder-sort": JSON.stringify({ key: "name", dir: "asc" }) } });
  assert.deepEqual(names(view), ["Missing", "Low", "High", "Zero"]);
  assert.match(view.tbody.innerHTML, /999/);
  assert.equal(view.headers.find((h) => h.key === "elo").attrs["aria-sort"], "descending");
});

test("empty and unavailable snapshots span all eight Home columns", async () => {
  assert.match(mount({ rows: [] }).tbody.innerHTML, /colspan="8"/);
  const view = mount({ inline: false, fail: true });
  await flush();
  assert.match(view.tbody.innerHTML, /colspan="8".*Could not load benchmark snapshot/);
});
