/**
 * Pages proxy route contract.
 * Keep in sync with proxy-routes.contract.json (Python contract tests read the JSON).
 * JS module form avoids JSON import attributes (Node 24 vs Wrangler).
 */
export default {
  proxy_path_prefixes: ["/api/v1/", "/api/games", "/api/play"],
  proxy_path_exact: [
    "/api/v1",
    "/api/contact",
    "/api/contact/",
    "/api/leaderboard/live",
    "/api/leaderboard/puzzles/live",
    "/api/leaderboard/identify/live",
  ],
  watch_asset_path_prefixes: ["/g/", "/p/", "/i/"],
  calibration_path_prefixes: ["/calibration/", "/api/calibration/"],
  calibration_path_exact: ["/calibration", "/api/calibration"],
  puzzle_set_path_exact: ["/puzzle-set", "/api/puzzle-set"],
  puzzle_set_path_prefixes: ["/puzzle-set/"],
  puzzle_set_api_path_prefixes: ["/api/puzzle-set/"],
};
