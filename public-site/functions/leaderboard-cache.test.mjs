import assert from "node:assert/strict";
import test from "node:test";

import {
  isLeaderboardLivePath,
  isLeaderboardSnapshotPath,
  isPagesOwnedApiPath,
  preferNewerSnapshot,
  rememberLeaderboardResponse,
  serveLeaderboardSnapshot,
  snapshotGeneratedAtMs,
  specForSnapshotPath,
} from "./_leaderboard_cache.js";

function memoryCache() {
  const store = new Map();
  return {
    async put(request, response) {
      store.set(request.url, response.clone());
    },
    async match(request) {
      const hit = store.get(request.url);
      return hit ? hit.clone() : undefined;
    },
  };
}

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

const OLD = {
  generated_at: "2026-08-16T18:49:21.000Z",
  agents: [{ id: "old", name: "Old", elo: 400, games: 1, provisional: true }],
};
const FRESH = {
  generated_at: "2026-09-07T00:28:04.000Z",
  agents: [{ id: "fresh", name: "Fresh", elo: 600, games: 4, provisional: true }],
};

test("live and snapshot paths are classified", () => {
  assert.equal(isLeaderboardLivePath("/api/leaderboard/live"), true);
  assert.equal(isLeaderboardLivePath("/api/leaderboard/puzzles/live"), true);
  assert.equal(isLeaderboardSnapshotPath("/api/leaderboard/snapshot"), true);
  assert.equal(isLeaderboardSnapshotPath("/api/leaderboard/puzzles/snapshot"), true);
  assert.equal(isLeaderboardSnapshotPath("/api/leaderboard/identify/snapshot"), true);
  assert.equal(isLeaderboardLivePath("/api/leaderboard/snapshot"), false);
  assert.equal(isLeaderboardSnapshotPath("/api/leaderboard/live"), false);
  assert.equal(isPagesOwnedApiPath("/api/edge-health"), true);
  assert.equal(isPagesOwnedApiPath("/api/leaderboard/snapshot"), true);
  assert.equal(isPagesOwnedApiPath("/api/v1/games"), false);
  assert.equal(specForSnapshotPath("/api/leaderboard/puzzles/snapshot").livePath, "/api/leaderboard/puzzles/live");
});

test("preferNewerSnapshot keeps the later generated_at", () => {
  assert.equal(snapshotGeneratedAtMs(FRESH) > snapshotGeneratedAtMs(OLD), true);
  assert.equal(preferNewerSnapshot(OLD, FRESH), FRESH);
  assert.equal(preferNewerSnapshot(FRESH, OLD), FRESH);
  assert.equal(preferNewerSnapshot(null, OLD), OLD);
  assert.equal(preferNewerSnapshot(FRESH, null), FRESH);
});

test("rememberLeaderboardResponse stores successful live JSON", async () => {
  const cache = memoryCache();
  const url = "https://chessvisionharness.pages.dev/api/leaderboard/live";
  await rememberLeaderboardResponse(url, "/api/leaderboard/live", jsonResponse(FRESH), cache);
  const served = await serveLeaderboardSnapshot({
    requestUrl: url,
    livePath: "/api/leaderboard/live",
    cache,
    assets: {
      async fetch() {
        return jsonResponse(OLD);
      },
    },
  });
  assert.equal(served.status, 200);
  assert.equal(served.headers.get("x-cvh-leaderboard"), "cache");
  const body = await served.json();
  assert.equal(body.generated_at, FRESH.generated_at);
  assert.equal(body.agents[0].id, "fresh");
});

test("rememberLeaderboardResponse ignores failed origin responses", async () => {
  const cache = memoryCache();
  const url = "https://chessvisionharness.pages.dev/api/leaderboard/live";
  await rememberLeaderboardResponse(
    url,
    "/api/leaderboard/live",
    jsonResponse({ ok: false, error: "Origin unreachable" }, 502),
    cache
  );
  const served = await serveLeaderboardSnapshot({
    requestUrl: url,
    livePath: "/api/leaderboard/live",
    cache,
    assets: {
      async fetch() {
        return jsonResponse(OLD);
      },
    },
  });
  const body = await served.json();
  assert.equal(served.headers.get("x-cvh-leaderboard"), "static");
  assert.equal(body.generated_at, OLD.generated_at);
});

test("snapshot prefers newer git JSON over an older cache hit", async () => {
  const cache = memoryCache();
  const url = "https://chessvisionharness.pages.dev/api/leaderboard/live";
  await rememberLeaderboardResponse(url, "/api/leaderboard/live", jsonResponse(OLD), cache);
  const served = await serveLeaderboardSnapshot({
    requestUrl: url,
    livePath: "/api/leaderboard/live",
    cache,
    assets: {
      async fetch() {
        return jsonResponse(FRESH);
      },
    },
  });
  const body = await served.json();
  assert.equal(served.headers.get("x-cvh-leaderboard"), "static");
  assert.equal(body.generated_at, FRESH.generated_at);
});

test("snapshot returns 404 when cache and assets are empty", async () => {
  const served = await serveLeaderboardSnapshot({
    requestUrl: "https://chessvisionharness.pages.dev/api/leaderboard/snapshot",
    livePath: "/api/leaderboard/live",
    cache: memoryCache(),
    assets: {
      async fetch() {
        return new Response("missing", { status: 404 });
      },
    },
  });
  assert.equal(served.status, 404);
});
