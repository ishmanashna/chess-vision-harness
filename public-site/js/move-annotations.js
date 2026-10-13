/* Saved finished-game analysis. Never exposes candidate moves or lines. */
const labels = {good: "Good", inaccuracy: "Inaccuracy", mistake: "Mistake", blunder: "Blunder"};
const escape = (text) => String(text).replace(/[&<>"']/g, (c) => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[c]);

export async function fetchSavedAnalysis(url, timeoutMs = 4000, fetcher = fetch) {
  const controller = new AbortController();
  let timer;
  const deadline = new Promise((_resolve, reject) => {
    timer = setTimeout(() => { controller.abort(); reject(new Error("Saved analysis timed out")); }, timeoutMs);
  });
  try {
    const operation = Promise.resolve().then(() => fetcher(url, {signal: controller.signal, cache: "no-store"}))
      .then((response) => { if (!response.ok) throw new Error("Saved analysis unavailable"); return response.json(); });
    return await Promise.race([operation, deadline]);
  } finally { clearTimeout(timer); }
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
  if (!row || !labels[row.label]) return "";
  return '<small class="move-quality is-' + row.label + '" title="Estimated mover win-chance loss: ' + escape(row.loss_percent) + ' percentage points">' + labels[row.label] + '</small>';
}

export function analysisSummary(analysis) {
  if (!analysis || analysis.status !== "complete") return analysis && analysis.reason || "Move analysis unavailable";
  const profile = analysis.profile || {};
  return "Estimated labels - " + (profile.engine || "Unknown engine") + ", depth " + profile.depth + ". Analysis budget not yet validated.";
}

export function detailText(row) {
  if (!row) return "Select a move to inspect its saved evaluation. Scores are from White's perspective.";
  const delta = row.before && row.after && Number.isFinite(row.before.cp) && Number.isFinite(row.after.cp)
    ? " | Change " + scoreText({cp: row.after.cp - row.before.cp}) : "";
  return "Ply " + row.ply + " (" + row.color + "): " + (labels[row.label] || "Unavailable") + " | White eval " + scoreText(row.before) + " to " + scoreText(row.after) + delta + " | Mover win-chance loss " + Number(row.loss_percent).toFixed(1) + " pp";
}

export function savedScore(analysis, ply) {
  if (!analysis || analysis.status !== "complete") return null;
  return ply === 0 && analysis.plies.length ? analysis.plies[0].before : (annotationAt(analysis, ply) || {}).after || null;
}
