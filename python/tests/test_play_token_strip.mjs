/** @jest-environment node */
/* Minimal contract test for play token persist-then-strip (Phase 8). */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import vm from "node:vm";

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, "../../public-site/js/play-api.js"), "utf8")
  .replace(/^export /gm, "")
  .replace(/import .*\n/g, "");

function loadPlayApi() {
  const sandbox = {
    window: {
      location: {
        pathname: "/play/game-abc",
        search: "",
        href: "http://localhost/play/game-abc",
      },
      history: { replaceState: () => {} },
      CVH: {
        humanGames: {
          get(id) {
            return sandbox._registry[id] || null;
          },
          upsert(entry) {
            sandbox._registry[entry.gameId] = entry;
          },
        },
      },
    },
    sessionStorage: {
      _data: {},
      getItem(k) {
        return this._data[k] || null;
      },
      setItem(k, v) {
        this._data[k] = v;
      },
    },
    URL,
    URLSearchParams,
    _registry: {},
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return sandbox;
}

function test(name, fn) {
  try {
    fn();
    console.log("ok", name);
  } catch (err) {
    console.error("fail", name, err);
    process.exitCode = 1;
  }
}

test("readPlayToken persists query token and strips URL", () => {
  const sandbox = loadPlayApi();
  let replaced = "";
  sandbox.window.location.search = "?token=secret-from-url";
  sandbox.window.location.href = "http://localhost/play/game-abc?token=secret-from-url";
  sandbox.window.history.replaceState = (_a, _b, url) => {
    replaced = url;
  };
  const token = sandbox.readPlayToken("game-abc");
  if (token !== "secret-from-url") throw new Error("expected query token");
  if (sandbox.sessionStorage.getItem("cvh-play-token:game-abc") !== "secret-from-url") {
    throw new Error("expected sessionStorage persist");
  }
  if (!replaced.includes("/play/game-abc") || replaced.includes("token=")) {
    throw new Error("expected stripped URL, got " + replaced);
  }
});

test("readPlayToken falls back to registry after strip", () => {
  const sandbox = loadPlayApi();
  sandbox._registry["game-abc"] = { gameId: "game-abc", token: "from-registry" };
  sandbox.window.location.search = "";
  const token = sandbox.readPlayToken("game-abc");
  if (token !== "from-registry") throw new Error("expected registry token");
  if (sandbox.sessionStorage.getItem("cvh-play-token:game-abc") !== "from-registry") {
    throw new Error("expected registry copied to session");
  }
});
