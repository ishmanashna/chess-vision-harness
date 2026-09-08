import { serveLeaderboardSnapshot } from "../../_leaderboard_cache.js";

/**
 * GET /api/leaderboard/snapshot — last-known-good ladder (Cache API, then git JSON).
 */
export async function onRequest(context) {
  return serveLeaderboardSnapshot({
    requestUrl: context.request.url,
    livePath: "/api/leaderboard/live",
    assets: context.env && context.env.ASSETS,
  });
}
