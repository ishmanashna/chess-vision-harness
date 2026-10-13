import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(new URL("move-annotations.js", import.meta.url), "utf8");
const {annotationAt, badgeHtml, scoreText, detailText, savedScore, analysisSummary, fetchSavedAnalysis} = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const row = {ply: 1, color: "black", label: "mistake", before: {cp: -20}, after: {cp: 100}, loss_percent: 10.7};
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
  assert.match(detailText(row), /black.*Mistake.*-0.20 to \+1.00.*Change \+1.20.*10.7 pp/);
  assert.match(badgeHtml(row), />Mistake</);
  assert.match(badgeHtml(row), /10.7 percentage points/);
});

test("mate scores preserve winner and do not claim a numeric delta", () => {
  assert.equal(scoreText({cp:null, mate:-3, winner:"black"}), "-M3");
  assert.equal(scoreText({cp:null, mate:0, winner:"white"}), "Checkmate (white)");
  assert.doesNotMatch(detailText({...row, after:{cp:null,mate:2,winner:"white"}}), /Change/);
  assert.equal(scoreText(null), "Unavailable");
});

test("labels have text and an explicit unvalidated-budget explanation", () => {
  assert.match(analysisSummary(analysis), /Fixture engine, depth 8.*not yet validated/);
  assert.equal(analysisSummary({status:"unavailable", reason:"Historical backfill deferred"}), "Historical backfill deferred");
  assert.equal(badgeHtml({...row,label:"<script>"}), "");
  assert.match(badgeHtml({...row,loss_percent:'"><script>'}), /&quot;&gt;&lt;script&gt;/);
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
  await assert.rejects(fetchSavedAnalysis("/annotations", 100, async () => ({ok:false})), /unavailable/);
});
