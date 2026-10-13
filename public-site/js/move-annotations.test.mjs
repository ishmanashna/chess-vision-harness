import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("move-annotations.js", import.meta.url), "utf8");
const {annotationAt, badgeHtml, scoreText, detailText, savedScore, analysisSummary, analysisFailure, fetchSavedAnalysis} = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const row = {ply: 1, color: "black", label: "mistake", before: {cp: -20}, after: {cp: 100}, loss_percent: 10.7, best_move_san:"Nf6"};
const analysis = {status: "complete", plies: [row], profile: {engine: "Fixture engine", depth: 8}};

test("annotations use exact one-based plies and do not attach unavailable data", () => {
  assert.equal(annotationAt(analysis, 1), row);
  assert.equal(annotationAt(analysis, 0), null);
  assert.equal(annotationAt(analysis, 2), null);
  assert.equal(annotationAt({status: "pending"}, 1), null);
  assert.equal(savedScore(analysis, 0), row.before);
  assert.equal(savedScore(analysis, 1), row.after);
});

test("evaluation changes stay White-relative while labels identify the mover", () => {
  assert.match(detailText(row), /White eval: -0.20 → \+1.00.*Δ \+1.20/);
  assert.match(badgeHtml(row), />\?</);
  assert.match(badgeHtml(row), /aria-label="Mistake"/);
  assert.match(badgeHtml(row), /Best move: Nf6/);
  assert.doesNotMatch(badgeHtml(row), /percentage points/);
});

test("mate scores preserve winner and do not claim a numeric delta", () => {
  assert.equal(scoreText({cp:null, mate:-3, winner:"black"}), "-M3");
  assert.equal(scoreText({cp:null, mate:0, winner:"white"}), "Checkmate (white)");
  assert.doesNotMatch(detailText({...row, after:{cp:null,mate:2,winner:"white"}}), /Δ/);
  assert.equal(scoreText(null), "Unavailable");
});

test("labels have text and an explicit unvalidated-budget explanation", () => {
  assert.match(analysisSummary(analysis), /Fixture engine, depth 8.*not yet validated/);
  assert.equal(analysisSummary({status:"unavailable", reason:"Historical backfill deferred"}), "Historical backfill deferred");
  assert.equal(badgeHtml({...row,label:"<script>"}), "");
  assert.equal(badgeHtml({...row,label:"good"}), "");
  assert.match(badgeHtml({...row,label:"inaccuracy"}), />\?!</);
  assert.match(badgeHtml({...row,label:"blunder"}), />\?\?</);
  assert.match(badgeHtml({...row,label:"great"}), />!</);
  assert.match(badgeHtml({...row,label:"brilliant"}), />!!</);
  assert.match(badgeHtml({...row,best_move_san:'"><script>'}), /&quot;&gt;&lt;script&gt;/);
});

test("the move list renders symbols without numeric evaluations", () => {
  const game = fs.readFileSync(new URL("spectator-game.js", import.meta.url), "utf8");
  assert.doesNotMatch(game, /evaluationHtml/);
  assert.doesNotMatch(badgeHtml(row), /move-evaluation/);
  assert.match(badgeHtml(row), />\?</);
});

test("an unclaimed draw after resignation uses contextual equality rather than a misleading blunder badge", () => {
  const badge = badgeHtml({...row,label:"blunder",terminal_context:{kind:"unclaimed_draw",reason:"threefold repetition",game_result:"0-1"}});
  assert.match(badge, />=</);
  assert.match(badge, /opponent resigned instead/);
  assert.doesNotMatch(badge, />\?\?</);
});

test("a hung analysis response body times out and aborts", async () => {
  let signal;
  await assert.rejects(fetchSavedAnalysis("/annotations", 15, async (_url, options) => {
    signal = options.signal;
    return {ok: true, json: () => new Promise(() => {})};
  }), /timed out/);
  assert.equal(signal.aborted, true);
});

test("missing analysis is rejected without manufacturing scores", async () => {
  await assert.rejects(fetchSavedAnalysis("/annotations", 100, async () => ({ok:false,status:404})), error => {
    assert.equal(error.status,404);
    assert.match(analysisFailure(error), /updated game server.*restart/);
    return true;
  });
  assert.match(analysisFailure(new Error("Saved analysis timed out")), /took too long/);
  assert.match(analysisFailure(new TypeError("Failed to fetch")), /Could not load/);
});
