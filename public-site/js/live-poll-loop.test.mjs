import assert from "node:assert/strict";
import test from "node:test";
import {
  createLivePollLoop,
  shouldPausePollWhenHidden,
  shouldSkipOverlappingPollTick,
} from "./live-poll-loop.js";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function mockDocument(hidden) {
  const listeners = {};
  return {
    hidden,
    addEventListener(name, fn) {
      listeners[name] = fn;
    },
    emit(name) {
      if (listeners[name]) listeners[name]();
    },
  };
}

test("shouldPausePollWhenHidden", () => {
  assert.equal(shouldPausePollWhenHidden(true), true);
  assert.equal(shouldPausePollWhenHidden(false), false);
});

test("shouldSkipOverlappingPollTick", () => {
  assert.equal(shouldSkipOverlappingPollTick(true), true);
  assert.equal(shouldSkipOverlappingPollTick(false), false);
});

test("hidden tab does not poll until visible", async () => {
  const doc = mockDocument(true);
  let calls = 0;
  const loop = createLivePollLoop({
    intervalMs: 40,
    document: doc,
    poll: async () => {
      calls += 1;
    },
  });
  loop.start();
  await sleep(120);
  assert.equal(calls, 0);
  doc.hidden = false;
  doc.emit("visibilitychange");
  await sleep(80);
  assert.ok(calls >= 1);
  loop.stop();
});

test("visible tab resumes polling after hide", async () => {
  const doc = mockDocument(false);
  let calls = 0;
  const loop = createLivePollLoop({
    intervalMs: 40,
    document: doc,
    poll: async () => {
      calls += 1;
    },
  });
  loop.start();
  await sleep(60);
  assert.ok(calls >= 1);
  doc.hidden = true;
  doc.emit("visibilitychange");
  const atHide = calls;
  await sleep(100);
  assert.equal(calls, atHide);
  doc.hidden = false;
  doc.emit("visibilitychange");
  await sleep(80);
  assert.ok(calls > atHide);
  loop.stop();
});

test("overlapping tick does not run concurrent polls", async () => {
  const doc = mockDocument(false);
  let calls = 0;
  let inPoll = false;
  const loop = createLivePollLoop({
    intervalMs: 20,
    document: doc,
    poll: async () => {
      assert.equal(inPoll, false, "poll ticks must not overlap");
      inPoll = true;
      calls += 1;
      await sleep(80);
      inPoll = false;
    },
  });
  loop.start();
  await sleep(200);
  assert.ok(calls >= 2, "expected sequential polls after slow ticks complete");
  loop.stop();
});
