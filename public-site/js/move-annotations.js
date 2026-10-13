/* Saved finished-game analysis; alternatives are shown only after the game. */
const labels = {good: "Good", great: "Great move", brilliant: "Brilliant move", inaccuracy: "Inaccuracy", mistake: "Mistake", blunder: "Blunder"};
const symbols = {great: "!", brilliant: "!!", inaccuracy: "?!", mistake: "?", blunder: "??"};
const escape = (text) => String(text).replace(/[&<>"']/g, (c) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[c]);

export async function fetchSavedAnalysis(url, timeoutMs = 4000, fetcher = fetch) {
  const controller = new AbortController();
  let timer;
  const deadline = new Promise((_resolve, reject) => {
    timer = setTimeout(() => { controller.abort(); reject(new Error("Saved analysis timed out")); }, timeoutMs);
  });
  try {
    const operation = Promise.resolve().then(() => fetcher(url, {signal: controller.signal, cache: "no-store"}))
      .then((response) => {
        if (!response.ok) throw Object.assign(new Error("Saved analysis HTTP " + response.status), {status: response.status});
        return response.json();
      });
    return await Promise.race([operation, deadline]);
  } finally { clearTimeout(timer); }
}

export function analysisFailure(error) {
  if (error && error.status === 404) return "Move annotations require an updated game server. The operator needs to restart the server.";
  if (error && /timed out/i.test(error.message)) return "Saved move analysis took too long to load. Replay is still available; reload to retry.";
  return "Could not load saved move analysis from the game server. Replay is still available; reload to retry.";
}

export function annotationAt(analysis, ply) {
  if (!analysis || analysis.status !== "complete" || ply < 1) return null;
  const row = analysis.plies && analysis.plies[ply - 1];
  return row && row.ply === ply ? row : null;
}

export function scoreText(score) {
  if (!score) return "Unavailable";
  if (score.mate != null) return score.mate === 0 ? "Checkmate (" + score.winner + ")" : (score.winner === "black" ? "-" : "+") + "M" + Math.abs(score.mate);
  if (!Number.isFinite(score.cp)) return "Unavailable";
  return (score.cp > 0 ? "+" : "") + (score.cp / 100).toFixed(2);
}

export function badgeHtml(row) {
  if (row && row.terminal_context && row.terminal_context.kind === "unclaimed_draw") {
    const context = row.terminal_context;
    const title = "Draw claim available by " + context.reason + ". The opponent resigned instead (" + context.game_result + ")." + (row.best_move_san ? " Best move: " + row.best_move_san + "." : "");
    return '<span class="move-quality is-draw-claim" aria-label="Draw claim available" title="' + escape(title) + '">=</span>';
  }
  if (!row || !symbols[row.label]) return "";
  const passes = row.exceptional && row.exceptional.passes || [];
  const verification = passes.length ? ". Verified depths: " + passes.map(pass => pass.depth).join(" / ") : "";
  const discovery = row.exceptional && row.exceptional.discovery;
  const discovered = discovery && discovery.discovered_depth
    ? discovery.root_changed === false
      ? ". Evaluation clarified through depth " + discovery.stable_through_depth
      : ". Deeper search discovery at depth " + discovery.discovered_depth
    : "";
  const positive = row.label === "great" || row.label === "brilliant";
  const preference = row.best_move_san ? ". Best move: " + row.best_move_san : ". Best move not saved yet";
  const title = labels[row.label] + ": " + scoreText(row.before) + " to " + scoreText(row.after) + (positive ? verification + discovered : preference);
  return '<span class="move-quality is-' + row.label + '" aria-label="' + labels[row.label] + '" title="' + escape(title) + '">' + symbols[row.label] + '</span>';
}

export function analysisSummary(analysis) {
  if (!analysis || analysis.status !== "complete") return analysis && analysis.reason || "Move analysis unavailable";
  const profile = analysis.profile || {};
  return "Estimated labels - " + (profile.engine || "Unknown engine") + ", depth " + profile.depth + ". Analysis budget not yet validated.";
}

export function detailText(row) {
  if (!row) return "";
  const delta = row.before && row.after && Number.isFinite(row.before.cp) && Number.isFinite(row.after.cp)
    ? " (Δ " + scoreText({cp: row.after.cp - row.before.cp}) + ")" : "";
  return "White eval: " + scoreText(row.before) + " → " + scoreText(row.after) + delta;
}

export function savedScore(analysis, ply) {
  if (!analysis || analysis.status !== "complete") return null;
  return ply === 0 && analysis.plies.length ? analysis.plies[0].before : (annotationAt(analysis, ply) || {}).after || null;
}
