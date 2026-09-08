import { serveLeaderboardSnapshot } from "../../../_leaderboard_cache.js";

/**
 * GET /api/leaderboard/puzzles/snapshot — last-known-good puzzle ladder.
 */
export async function onRequest(context) {
  return serveLeaderboardSnapshot({
    requestUrl: context.request.url,
    livePath: "/api/leaderboard/puzzles/live",
    assets: context.env && context.env.ASSETS,
  });
}
