import { serveLeaderboardSnapshot } from "../../../_leaderboard_cache.js";

/**
 * GET /api/leaderboard/identify/snapshot — last-known-good identify ladder.
 */
export async function onRequest(context) {
  return serveLeaderboardSnapshot({
    requestUrl: context.request.url,
    livePath: "/api/leaderboard/identify/live",
    assets: context.env && context.env.ASSETS,
  });
}
