(function () {
  "use strict";

  var HEALTH_URL = "/api/edge-health";
  var LIVE_LEADERBOARD_URL = "/api/leaderboard/live";
  var SNAPSHOT_LEADERBOARD_URL = "/data/leaderboard.json";
  var THEME_KEY = "chess-harness-theme";
  var PROVISIONAL_HINT =
    "Provisional — K has not returned to the stable factor (24) yet. Ratings stabilize after 100 rated games.";
  var PERFORMANCE_TIP =
    "Estimated strength from move accuracy via the calibration accuracy→Elo table — not ladder Elo.";
  var ENGINES_JS_VERSION = "3";
  var HOME_SORT_KEY = "cvh-home-ladder-sort";
  var AGENTS_SORT_KEY = "cvh-leaderboard-agents-sort";
  var healthCache = null;
  var liveLeaderboardListeners = [];
  var latestLiveLeaderboard = null;

  function navPath() {
    var path = window.location.pathname.replace(/\/+$/, "") || "/";
    return path;
  }

  function setActiveNav() {
    var current = navPath();
    var map = {
      "/": "nav-home",
      "/leaderboard": "nav-leaderboard",
      "/contact": "nav-contact",
      "/create": "nav-create",
      "/human": "nav-human",
      "/spectator": "nav-spectator",
      "/active": "nav-spectator",
      "/completed": "nav-spectator",
      "/calibration": "nav-calibration",
    };
    var activeId = map[current];
    if (!activeId && current.indexOf("/g/") === 0) activeId = "nav-spectator";
    if (!activeId && current.indexOf("/p/") === 0) activeId = "nav-spectator";
    if (!activeId && current.indexOf("/i/") === 0) activeId = "nav-spectator";
    if (!activeId && current.indexOf("/play/") === 0) activeId = "nav-human";
    if (!activeId) return;
    var link = document.getElementById(activeId);
    if (link) link.classList.add("active");
  }

  /** Localhost only: show Calibration after Leaderboard (never on Pages). */
  function isLoopbackHost() {
    var host = window.location.hostname;
    return (
      host === "127.0.0.1" ||
      host === "localhost" ||
      host === "::1" ||
      host === "[::1]"
    );
  }

  function ensureCalibrationNav() {
    if (document.getElementById("nav-calibration")) {
      if (navPath() === "/calibration") {
        document.getElementById("nav-calibration").classList.add("active");
      }
      return;
    }
    if (!isLoopbackHost()) return;
    var leaderboard = document.getElementById("nav-leaderboard");
    if (!leaderboard || !leaderboard.parentNode) return;
    var a = document.createElement("a");
    a.href = "/calibration";
    a.id = "nav-calibration";
    a.textContent = "Calibration";
    leaderboard.parentNode.insertBefore(a, leaderboard.nextSibling);
    if (navPath() === "/calibration") a.classList.add("active");
  }

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark"
      ? "dark"
      : "light";
  }

  function applyTheme(theme) {
    var t = theme === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", t);
    try {
      localStorage.setItem(THEME_KEY, t);
    } catch (_err) {}
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.textContent = t === "dark" ? "Light mode" : "Dark mode";
      btn.setAttribute(
        "aria-label",
        t === "dark" ? "Switch to light mode" : "Switch to dark mode"
      );
    });
  }

  function initThemeToggle() {
    applyTheme(currentTheme());
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        applyTheme(currentTheme() === "dark" ? "light" : "dark");
      });
    });
  }

  function formatElo(agent) {
    var elo = agent.elo;
    var provisional = isProvisional(agent);
    if (elo == null || elo === "") return "—";
    return provisional ? String(elo) + "*" : String(elo);
  }

  function isProvisional(agent) {
    // Prefer server boolean; never derive from display Games (scored includes AvH).
    if (typeof agent.provisional === "boolean") return agent.provisional;
    return true;
  }

  function sortAgents(agents) {
    return agents.slice().sort(function (a, b) {
      var eloA = Number(a.elo) || 0;
      var eloB = Number(b.elo) || 0;
      if (eloB !== eloA) return eloB - eloA;
      return String(a.name || a.id).localeCompare(String(b.name || b.id));
    });
  }

  var AGENT_NUMERIC_KEYS = ["elo", "mean_accuracy", "mean_play_rating", "games"];

  function normalizeAgentRow(agent) {
    return {
      id: agent.id || "",
      name: agent.name || agent.id || "—",
      elo: agent.elo,
      mean_accuracy: agent.mean_accuracy,
      mean_play_rating: agent.mean_play_rating,
      games: Number(agent.games) || 0,
      provisional: agent.provisional,
      _raw: agent,
    };
  }

  function sortAgentRows(rows, key, dir) {
    var ts = window.CVH && window.CVH.tableSort;
    if (!ts || !key) {
      return sortAgents(
        rows.map(function (r) {
          return r._raw || r;
        })
      ).map(normalizeAgentRow);
    }
    return ts.sortRows(rows, key, dir, {
      numericKeys: AGENT_NUMERIC_KEYS,
      tieKey: "id",
    });
  }

  function defaultAgentSortDir(key) {
    if (AGENT_NUMERIC_KEYS.indexOf(key) !== -1) return "desc";
    return "asc";
  }

  function normalizeLeaderboardPayload(data, live) {
    data.agents = Array.isArray(data.agents) ? data.agents : [];
    data.opponents = Array.isArray(data.opponents) ? data.opponents : [];
    data.live = live === true;
    return data;
  }

  function fetchLeaderboardSnapshot() {
    return fetch(SNAPSHOT_LEADERBOARD_URL, { cache: "no-cache" }).then(function (res) {
      if (!res.ok) throw new Error("leaderboard snapshot fetch failed");
      return res.json();
    });
  }

  function fetchLeaderboard() {
    return checkEdgeHealth().then(function (health) {
      if (!health.online) {
        return fetchLeaderboardSnapshot().then(function (data) {
          return normalizeLeaderboardPayload(data, false);
        });
      }
      return fetch(LIVE_LEADERBOARD_URL, { cache: "no-cache" })
        .then(function (res) {
          if (!res.ok) throw new Error("live leaderboard fetch failed");
          return res.json();
        })
        .then(function (data) {
          var live = normalizeLeaderboardPayload(data, true);
          notifyLiveLeaderboard(live);
          return live;
        })
        .catch(function () {
          return fetchLeaderboardSnapshot().then(function (data) {
            return normalizeLeaderboardPayload(data, false);
          });
        });
    });
  }

  function notifyLiveLeaderboard(payload) {
    latestLiveLeaderboard = payload;
    liveLeaderboardListeners.slice().forEach(function (cb) {
      try {
        cb(payload);
      } catch (_err) {}
    });
  }

  function onLiveLeaderboard(cb) {
    if (typeof cb === "function") liveLeaderboardListeners.push(cb);
    return function () {
      var i = liveLeaderboardListeners.indexOf(cb);
      if (i !== -1) liveLeaderboardListeners.splice(i, 1);
    };
  }

  function getLatestLiveLeaderboard() {
    return latestLiveLeaderboard;
  }

  function formatQualityMean(value, suffix) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (isNaN(n)) return "—";
    if (suffix) return String(n) + suffix;
    // Performance (and other bare ratings): whole numbers only.
    return String(Math.round(n));
  }

  function leaderboardColCount(fullColumns, showModelId) {
    var n = fullColumns ? 6 : 4;
    if (showModelId) n += 1;
    return n;
  }

  function renderLeaderboardRows(agents, limit, fullColumns, showModelId, sortKey, sortDir) {
    var rows = (Array.isArray(agents) ? agents : []).map(normalizeAgentRow);
    var sorted = sortAgentRows(rows, sortKey, sortDir);
    var slice = typeof limit === "number" ? sorted.slice(0, limit) : sorted;
    var colCount = leaderboardColCount(fullColumns, showModelId);
    if (!slice.length) {
      return (
        '<tr><td colspan="' +
        colCount +
        '" class="empty-state">No rated agents yet. When games finish, the ladder snapshot will appear here.</td></tr>'
      );
    }
    return slice
      .map(function (row, index) {
        var agent = row._raw || row;
        var rank = index + 1;
        var name = row.name || "—";
        var games = row.games;
        var provisional = isProvisional(agent);
        var eloClass = provisional ? "elo provisional" : "elo";
        var titleAttr = provisional
          ? ' title="' + escapeHtml(PROVISIONAL_HINT) + '"'
          : "";
        var accCell = fullColumns
          ? "<td>" +
            escapeHtml(formatQualityMean(agent.mean_accuracy, "%")) +
            "</td>"
          : "";
        var playCell = fullColumns
          ? '<td title="' +
            escapeHtml(PERFORMANCE_TIP) +
            '">' +
            escapeHtml(formatQualityMean(agent.mean_play_rating)) +
            "</td>"
          : "";
        var modelCell = showModelId
          ? "<td><code>" + escapeHtml(agent.id || "") + "</code></td>"
          : "";
        return (
          "<tr>" +
          '<td class="rank">' +
          rank +
          "</td>" +
          "<td>" +
          escapeHtml(name) +
          "</td>" +
          '<td class="' +
          eloClass +
          '"' +
          titleAttr +
          ">" +
          escapeHtml(formatElo(agent)) +
          "</td>" +
          accCell +
          playCell +
          "<td>" +
          games +
          "</td>" +
          modelCell +
          "</tr>"
        );
      })
      .join("");
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatGeneratedAt(iso) {
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return "";
      return d.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
    } catch (_err) {
      return "";
    }
  }

  function mountLeaderboardTable(container, options) {
    options = options || {};
    var limit = options.limit;
    var showMeta = options.showMeta !== false;
    var fullColumns =
      options.fullColumns === true ||
      container.hasAttribute("data-leaderboard-full");
    var showModelId =
      options.showModelId === true ||
      container.hasAttribute("data-show-model-id");
    var table = container.querySelector("table");
    var tbody = container.querySelector("tbody");
    var ts = window.CVH && window.CVH.tableSort;
    var storageKey = showModelId ? AGENTS_SORT_KEY : HOME_SORT_KEY;
    var state = ts
      ? ts.loadState(storageKey, { key: "elo", dir: "desc" }, { estimatedElo: "mean_play_rating" })
      : { key: "elo", dir: "desc" };
    // Map legacy Performance key name if someone stored "performance".
    if (state.key === "performance" || state.key === "estimatedElo") {
      state.key = "mean_play_rating";
    }
    if (state.key === "accuracy") state.key = "mean_accuracy";
    var sortKey = state.key || "elo";
    var sortDir = state.dir;
    var cache = [];

    function paint() {
      if (!tbody) return;
      tbody.innerHTML = renderLeaderboardRows(
        cache,
        limit,
        fullColumns,
        showModelId,
        sortKey,
        sortDir
      );
      if (ts) ts.paintHeaders(table, sortKey, sortDir);
    }

    if (table && ts && !table._cvhSortBound) {
      table._cvhSortBound = true;
      ts.bindHeaders(table, {
        getKey: function () {
          return sortKey;
        },
        getDir: function () {
          return sortDir;
        },
        setSort: function (key, dir) {
          sortKey = key;
          sortDir = dir;
          ts.saveState(storageKey, sortKey, sortDir);
        },
        defaultDirForKey: defaultAgentSortDir,
        onChange: paint,
      });
    }

    function updateLeaderboardMeta(data) {
      if (!showMeta) return;
      var meta = container.querySelector("[data-snapshot-meta]");
      if (!meta) return;
      var when = formatGeneratedAt(data.generated_at);
      if (data.live) {
        meta.textContent = when
          ? "Live ladder · updated " + when + "."
          : "Live ladder.";
      } else {
        meta.textContent = when
          ? "Snapshot from " + when + "."
          : "Leaderboard snapshot.";
      }
    }

    function paintData(data) {
      cache = Array.isArray(data.agents) ? data.agents : [];
      paint();
      updateLeaderboardMeta(data);
    }

    function upgradeToLive() {
      var controller = new AbortController();
      var timeout = setTimeout(function () {
        controller.abort();
      }, 6000);
      checkEdgeHealth()
        .then(function (health) {
          if (!health.online) return null;
          return fetch(LIVE_LEADERBOARD_URL, {
            cache: "no-cache",
            signal: controller.signal,
          })
            .then(function (res) {
              if (!res.ok) throw new Error("live leaderboard fetch failed");
              return res.json();
            })
            .then(function (raw) {
              return normalizeLeaderboardPayload(raw, true);
            })
            .then(function (data) {
              paintData(data);
              notifyLiveLeaderboard(data);
            });
        })
        .catch(function () {
          return null;
        })
        .then(function () {
          clearTimeout(timeout);
        });
    }

    fetchLeaderboardSnapshot()
      .then(function (raw) {
        return normalizeLeaderboardPayload(raw, false);
      })
      .then(function (data) {
        paintData(data);
        upgradeToLive();
      })
      .catch(function () {
        if (tbody) {
          var colCount = leaderboardColCount(fullColumns, showModelId);
          tbody.innerHTML =
            '<tr><td colspan="' +
            colCount +
            '" class="empty-state">Could not load leaderboard snapshot.</td></tr>';
        }
      });
  }

  function setStatusChip(state, detail) {
    document.querySelectorAll("[data-status-chip]").forEach(function (chip) {
      chip.dataset.state = state;
      var label = chip.querySelector("[data-status-label]");
      if (label) {
        label.textContent = state === "online" ? "Online" : "Sleeping";
      }
      chip.title =
        detail ||
        (state === "online"
          ? "Game server online"
          : "Game server offline — leaderboard uses the last snapshot");
    });
  }

  function checkEdgeHealth() {
    if (healthCache) {
      return Promise.resolve(healthCache);
    }
    return fetch(HEALTH_URL, { cache: "no-cache" })
      .then(function (res) {
        if (!res.ok) throw new Error("health unavailable");
        return res.json();
      })
      .then(function (data) {
        var online =
          data && (data.status === "online" || data.online === true);
        healthCache = { online: online, raw: data };
        return healthCache;
      })
      .catch(function () {
        healthCache = { online: false, raw: null };
        return healthCache;
      });
  }

  function applyHealthUi(options) {
    options = options || {};
    return checkEdgeHealth().then(function (health) {
      var online = health.online;
      setStatusChip(
        online ? "online" : "sleeping",
        online
          ? "Game server online — Create Game and live boards available"
          : "Game server offline — leaderboard uses the last snapshot"
      );
      document.querySelectorAll("[data-requires-origin]").forEach(function (el) {
        el.hidden = !online;
      });
      document.querySelectorAll("[data-offline-only]").forEach(function (el) {
        el.hidden = online;
      });
      if (options.onHealth) options.onHealth(health);
      return health;
    });
  }

  function loadScriptOnce(src) {
    if (document.querySelector('script[src="' + src + '"]')) return;
    var script = document.createElement("script");
    script.src = src;
    document.body.appendChild(script);
  }

  function loadEnginesOnce() {
    var src = "/js/engines.js?v=" + ENGINES_JS_VERSION;
    if (document.querySelector('script[src^="/js/engines.js"]')) return;
    var script = document.createElement("script");
    script.src = src;
    script.onload = function () {
      document.querySelectorAll("[data-engines-leaderboard]").forEach(function (root) {
        if (window.CVH && typeof window.CVH.mountEnginesTable === "function") {
          window.CVH.mountEnginesTable(root);
        }
      });
    };
    document.body.appendChild(script);
  }

  function nameWithoutElo(value) {
    return String(value || "").replace(/\s*\(\d+\)\s*$/, "").trim();
  }

  /** Shorten Stockfish catalog tag inside parentheses; leave other tags alone. */
  function shortenEngineTag(tag) {
    var t = String(tag || "").trim();
    var depthNoise = t.match(/^depth\s+(\d+)\s*\+\s*(\d+)%\s*noise$/i);
    if (depthNoise) return "d" + depthNoise[1] + "+" + depthNoise[2] + "%";
    var depthOnly = t.match(/^depth\s+(\d+)$/i);
    if (depthOnly) return "d" + depthOnly[1];
    var noiseOnly = t.match(/^(\d+)%\s*noise$/i);
    if (noiseOnly) return noiseOnly[1] + "% noise";
    var skill = t.match(/^Skill\s+(-?\d+)$/i);
    if (skill) return "Skill " + skill[1];
    return t;
  }

  /** Shorten Stockfish catalog labels for lists and /g/; leave agent names alone. */
  function abbreviateListName(value) {
    var s = nameWithoutElo(value);
    var tagged = s.match(/^Stockfish\s+\d+(?:\.\d+)?\s*\((.+)\)$/i);
    if (tagged) return shortenEngineTag(tagged[1]);
    var bare = s.match(/^Stockfish\s+(\d+(?:\.\d+)?)$/i);
    if (bare) return "SF " + bare[1];
    return s;
  }

  window.CVH = window.CVH || {};
  window.CVH.applyHealthUi = applyHealthUi;
  window.CVH.mountLeaderboardTable = mountLeaderboardTable;
  window.CVH.fetchLeaderboard = fetchLeaderboard;
  window.CVH.fetchLeaderboardSnapshot = fetchLeaderboardSnapshot;
  window.CVH.onLiveLeaderboard = onLiveLeaderboard;
  window.CVH.getLatestLiveLeaderboard = getLatestLiveLeaderboard;
  window.CVH.formatElo = formatElo;
  window.CVH.formatQualityMean = formatQualityMean;
  window.CVH.isProvisional = isProvisional;
  window.CVH.nameWithoutElo = nameWithoutElo;
  window.CVH.abbreviateListName = abbreviateListName;

  document.addEventListener("DOMContentLoaded", function () {
    setActiveNav();
    ensureCalibrationNav();
    initThemeToggle();
    if (document.querySelector("[data-status-chip]")) {
      applyHealthUi();
    }
    document.querySelectorAll("[data-leaderboard]").forEach(function (root) {
      var limitAttr = root.getAttribute("data-limit");
      var limit = limitAttr ? parseInt(limitAttr, 10) : undefined;
      mountLeaderboardTable(root, { limit: limit, showMeta: true });
    });
    if (document.querySelector("[data-engines-leaderboard]")) {
      loadEnginesOnce();
    }
    // Pages OAuth only — skip on origin calibration to avoid /auth/me 404 noise.
    if (navPath() !== "/calibration") {
      loadScriptOnce("/js/auth.js");
    }
  });
})();
