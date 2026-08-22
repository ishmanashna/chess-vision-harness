import assert from "node:assert/strict";
import test from "node:test";
import { shouldFetchLive } from "./live-health-gate.js";

test("shouldFetchLive is false when origin is not online", () => {
  assert.equal(shouldFetchLive(null), false);
  assert.equal(shouldFetchLive(undefined), false);
  assert.equal(shouldFetchLive({}), false);
  assert.equal(shouldFetchLive({ online: false }), false);
});

test("shouldFetchLive is true only when online", () => {
  assert.equal(shouldFetchLive({ online: true }), true);
  assert.equal(shouldFetchLive({ online: true, raw: {} }), true);
});
