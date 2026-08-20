(function () {
  "use strict";

  var HEALTH_URL = "/api/edge-health";
  var FETCH_TIMEOUT_MS = 12000;
  var HEALTH_POLL_MS = 15000;
  var HEALTH_POLL_SLEEPING_MS = 4000;
  var HEALTH_STORAGE_KEY = "cvh-edge-health-v1";
  /** Optimistic Online paint if last probe was within this window (ms). */
  var HEALTH_FRESH_MS = 90000;
  var LIVE_LEADERBOARD_URL = "/api/leaderboard/live";
  var SNAPSHOT_LEADERBOARD_URL = "/data/leaderboard.json";
  var THEME_KEY = "chess-harness-theme";
  var PROVISIONAL_HINT =
    "Provisional — K has not returned to the stable factor (24) yet. Ratings stabilize after 100 rated games.";
  var PERFORMANCE_TIP =
    "Move-by-move strength on the Elo scale, from mean accuracy via the calibration accuracy-to-Elo table. Separate from ladder Elo; never changes it.";
  var OBSERVATION_TEXT_TIP =
    "Text-only agent — plays from the board.txt grid, not the PNG image.";
  var ENGINES_JS_VERSION = "4";
  var SITE_JS_VERSION = "5";
  var HOME_SORT_KEY = "cvh-home-ladder-sort";
  var AGENTS_SORT_KEY = "cvh-leaderboard-agents-sort";
  var healthCache = null;
  var healthInflight = null;
  var healthPollTimer = null;
  var healthPollStarted = false;
  var lastPaintedOnline = null;
  var healthUiListeners = [];
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
      "/launch": "nav-create",
      "/create": "nav-create",
      "/spectator": "nav-spectator",
      "/active": "nav-spectator",
      "/completed": "nav-spectator",
      "/calibration": "nav-calibration",
    };
    var activeId = map[current];
    if (!activeId && current.indexOf("/g/") === 0) activeId = "nav-spectator";
    if (!activeId && current.indexOf("/p/") === 0) activeId = "nav-spectator";
    if (!activeId && current.indexOf("/i/") === 0) activeId = "nav-spectator";
    if (!activeId && current.indexOf("/play/") === 0) activeId = "nav-create";
    if (!activeId && current.indexOf("/puzzle-set/") === 0) activeId = "nav-puzzle-set";
    if (!activeId && current === "/puzzle-set") activeId = "nav-puzzle-set";
    var link = document.getElementById(activeId);
    if (link) link.classList.add("active");
  }

  /** Localhost only: show Calibration after Leaderboards (never on Pages). */
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

  function ensurePuzzleSetNav() {
    if (document.getElementById("nav-puzzle-set")) {
      if (navPath() === "/puzzle-set") {
        document.getElementById("nav-puzzle-set").classList.add("active");
      }
      return;
    }
    if (!isLoopbackHost()) return;
    var calibration = document.getElementById("nav-calibration");
    var anchor = calibration || document.getElementById("nav-leaderboard");
    if (!anchor || !anchor.parentNode) return;
    var a = document.createElement("a");
    a.href = "/puzzle-set";
    a.id = "nav-puzzle-set";
    a.textContent = "Puzzle set";
    anchor.parentNode.insertBefore(a, calibration ? calibration.nextSibling : anchor.nextSibling);
    if (navPath() === "/puzzle-set") a.classList.add("active");
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

  var AGENT_NUMERIC_KEYS = [
    "elo",
    "mean_accuracy",
    "mean_play_rating",
    "games",
    "puzzle_rating",
    "puzzle_attempts",
    "puzzle_solves",
    "puzzle_solve_ratio",
    "identify_attempts",
    "identify_full",
    "identify_full_ratio",
    "identify_mean_accuracy",
    "identify_full_position_rate",
  ];

  function normalizeAgentRow(agent) {
    return {
      id: agent.id || "",
      name: agent.name || agent.id || "—",
      elo: agent.elo,
      mean_accuracy: agent.mean_accuracy,
      mean_play_rating: agent.mean_play_rating,
      games: Number(agent.games) || 0,
      provisional: agent.provisional,
      puzzle_rating: agent.puzzle_rating,
      puzzle_attempts: Number(agent.puzzle_attempts) || 0,
      puzzle_solves: Number(agent.puzzle_solves) || 0,
      puzzle_solve_ratio: puzzleSolveRatio(
        agent.puzzle_solves,
        agent.puzzle_attempts
      ),
      identify_attempts: Number(agent.identify_attempts) || 0,
      identify_full: Number(agent.identify_full) || 0,
      identify_full_ratio: identifyFullRatio(
        agent.identify_full,
        agent.identify_attempts
      ),
      identify_mean_accuracy: agent.identify_mean_accuracy,
      identify_full_position_rate: agent.identify_full_position_rate,
      observation: agent.observation || "vision",
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

  function fetchWithTimeout(url, options, timeoutMs) {
    options = options || {};
    var ms = typeof timeoutMs === "number" ? timeoutMs : FETCH_TIMEOUT_MS;
    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort();
    }, ms);
    var fetchOptions = Object.assign({}, options, { signal: controller.signal });
    return fetch(url, fetchOptions).then(
      function (res) {
        clearTimeout(timer);
        return res;
      },
      function (err) {
        clearTimeout(timer);
        throw err;
      }
    );
  }

  function fetchLeaderboardSnapshot() {
    if (window.CVH_INLINE_SNAPSHOT) {
      return Promise.resolve(window.CVH_INLINE_SNAPSHOT);
    }
    return fetchWithTimeout(SNAPSHOT_LEADERBOARD_URL, { cache: "no-cache" }, FETCH_TIMEOUT_MS).then(function (res) {
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

  var SPECIALTY_CACHE_TTL_MS = 60000;
  var specialtyLeaderboardCache = { puzzles: null, identify: null };

  function fetchSpecialtyLeaderboard(kind) {
    var now = Date.now();
    var hit = specialtyLeaderboardCache[kind];
    if (hit && now - hit.ts < SPECIALTY_CACHE_TTL_MS) {
      return Promise.resolve(hit.data);
    }
    var liveUrl =
      kind === "puzzles"
        ? "/api/leaderboard/puzzles/live"
        : "/api/leaderboard/identify/live";
    var snapUrl =
      kind === "puzzles"
        ? "/data/puzzles_leaderboard.json"
        : "/data/identify_leaderboard.json";
    return checkEdgeHealth().then(function (health) {
      if (!health.online) {
        return fetchWithTimeout(snapUrl, { cache: "no-cache" }, FETCH_TIMEOUT_MS).then(
          function (res) {
            if (!res.ok) throw new Error("specialty snapshot fetch failed");
            return res.json();
          }
        );
      }
      return fetch(liveUrl, { cache: "no-cache" })
        .then(function (res) {
          if (!res.ok) throw new Error("specialty live fetch failed");
          return res.json();
        })
        .catch(function () {
          return fetchWithTimeout(snapUrl, { cache: "no-cache" }, FETCH_TIMEOUT_MS).then(
            function (res) {
              if (!res.ok) throw new Error("specialty snapshot fetch failed");
              return res.json();
            }
          );
        });
    }).then(function (data) {
      specialtyLeaderboardCache[kind] = { ts: Date.now(), data: data };
      return data;
    });
  }

  function formatQualityMean(value, suffix) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (isNaN(n)) return "—";
    if (suffix === "%") return n.toFixed(2) + "%";
    if (suffix) return String(n) + suffix;
    // Performance (and other bare ratings): whole numbers only.
    return String(Math.round(n));
  }

  /** Fraction (0..1) displayed as a percentage, or "—" when absent. */
  function formatRatePct(value) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (isNaN(n)) return "—";
    return (n * 100).toFixed(2) + "%";
  }

  function leaderboardColCount(fullColumns, showModelId, unified, homeBenchmark) {
    var n = fullColumns ? (homeBenchmark ? 7 : 6) : 4;
    if (unified) n += 5;
    if (showModelId) n += 1;
    return n;
  }

  function formatCount(value) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    return isNaN(n) ? "—" : String(n);
  }

  function puzzleSolveRatio(solves, attempts) {
    var a = Number(attempts) || 0;
    var s = Number(solves) || 0;
    if (a <= 0) return null;
    return s / a;
  }

  function formatPuzzleRatio(solves, attempts) {
    var a = Number(attempts) || 0;
    var s = Number(solves) || 0;
    if (a <= 0) return "—";
    return s + "/" + a;
  }

  function identifyFullRatio(full, attempts) {
    var a = Number(attempts) || 0;
    var f = Number(full) || 0;
    if (a <= 0) return null;
    return f / a;
  }

  function formatIdentifyRatio(full, attempts) {
    var a = Number(attempts) || 0;
    var f = Number(full) || 0;
    if (a <= 0) return "—";
    return f + "/" + a;
  }

  function formatAgentNameCell(name, observation) {
    var label = escapeHtml(name || "—");
    if (observation === "text") {
      return (
        label +
        ' <span class="observation-mark" title="' +
        escapeHtml(OBSERVATION_TEXT_TIP) +
        '">text</span>'
      );
    }
    return label;
  }

  function renderLeaderboardRows(
    agents,
    limit,
    fullColumns,
    showModelId,
    unified,
    homeBenchmark,
    sortKey,
    sortDir
  ) {
    var rows = (Array.isArray(agents) ? agents : []).map(normalizeAgentRow);
    var sorted = sortAgentRows(rows, sortKey, sortDir);
    var slice = typeof limit === "number" ? sorted.slice(0, limit) : sorted;
    var colCount = leaderboardColCount(fullColumns, showModelId, unified, homeBenchmark);
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
        var eloClass = homeBenchmark
          ? ""
          : provisional
            ? "elo provisional"
            : "elo";
        var titleAttr =
          !homeBenchmark && provisional
            ? ' title="' + escapeHtml(PROVISIONAL_HINT) + '"'
            : "";
        var accCell = fullColumns
          ? "<td>" +
            escapeHtml(formatQualityMean(agent.mean_accuracy, "%")) +
            "</td>"
          : "";
        var playCell = fullColumns
          ? (homeBenchmark
              ? "<td>" +
                escapeHtml(formatQualityMean(agent.mean_play_rating)) +
                "</td>"
              : '<td title="' +
                escapeHtml(PERFORMANCE_TIP) +
                '">' +
                escapeHtml(formatQualityMean(agent.mean_play_rating)) +
                "</td>")
          : "";
        var gamesCell = homeBenchmark
          ? ""
          : "<td>" + games + "</td>";
        var homeBenchmarkCells = homeBenchmark
          ? "<td>" +
            escapeHtml(
              row.puzzle_rating == null ? "—" : formatQualityMean(row.puzzle_rating)
            ) +
            "</td>" +
            "<td>" +
            escapeHtml(formatRatePct(row.identify_mean_accuracy)) +
            "</td>"
          : "";
        var unifiedCells = unified
          ? '<td title="' +
            escapeHtml("Glicko-2 puzzle rating from finished attempts — separate from ladder Elo and never affects it.") +
            '">' +
            escapeHtml(row.puzzle_rating == null ? "—" : formatQualityMean(row.puzzle_rating)) +
            "</td>" +
            "<td title=\"" +
            escapeHtml("Puzzle solves over finished attempts (e.g. 2/5). Sorted by solve rate.") +
            '">' +
            escapeHtml(formatPuzzleRatio(row.puzzle_solves, row.puzzle_attempts)) +
            "</td>" +
            "<td title=\"" +
            escapeHtml("Full-position identifications over finished attempts (e.g. 1/4). Sorted by rate.") +
            '">' +
            escapeHtml(formatIdentifyRatio(row.identify_full, row.identify_attempts)) +
            "</td>" +
            "<td>" +
            escapeHtml(formatRatePct(row.identify_mean_accuracy)) +
            "</td>" +
            "<td>" +
            escapeHtml(formatRatePct(row.identify_full_position_rate)) +
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
          formatAgentNameCell(name, agent.observation) +
          "</td>" +
          "<td" +
          (eloClass ? ' class="' + eloClass + '"' : "") +
          titleAttr +
          ">" +
          escapeHtml(formatElo(agent)) +
          "</td>" +
          accCell +
          playCell +
          gamesCell +
          homeBenchmarkCells +
          unifiedCells +
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
    var unified =
      options.unified === true ||
      container.hasAttribute("data-show-unified-stats");
    var homeBenchmark =
      options.homeBenchmark === true ||
      container.hasAttribute("data-show-home-benchmark");
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
        unified,
        homeBenchmark,
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
          : "Leaderboards snapshot.";
      }
    }

    function paintData(data) {
      cache = Array.isArray(data.agents) ? data.agents : [];
      paint();
      updateLeaderboardMeta(data);
    }

    function showLiveUpgradeError() {
      if (!showMeta) return;
      var meta = container.querySelector("[data-snapshot-meta]");
      if (!meta) return;
      meta.textContent =
        "Live ladder update failed — puzzle and identify cells may be stale. Refresh or try again.";
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
            })
            .catch(function () {
              showLiveUpgradeError();
              return null;
            });
        })
        .catch(function () {
          return null;
        })
        .then(function () {
          clearTimeout(timeout);
        });
    }

    onHealthUi(function (health, meta) {
      if (health && health.online && meta && meta.becameOnline) upgradeToLive();
    });

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
          var colCount = leaderboardColCount(fullColumns, showModelId, unified, homeBenchmark);
          tbody.innerHTML =
            '<tr><td colspan="' +
            colCount +
            '" class="empty-state">Could not load benchmark snapshot.</td></tr>';
        }
      });
  }

  function setStatusChip(state, detail) {
    document.querySelectorAll("[data-status-chip]").forEach(function (chip) {
      chip.dataset.state = state;
      var label = chip.querySelector("[data-status-label]");
      if (label) {
        label.textContent =
          state === "online"
            ? "Online"
            : state === "checking"
              ? "Checking…"
              : "Sleeping";
      }
      chip.title =
        detail ||
        (state === "online"
          ? "Game server online"
          : state === "checking"
            ? "Checking whether the game server is reachable…"
            : "Game server offline — leaderboard uses the last snapshot");
    });
  }

  function applyHealthVisibility(online) {
    document.querySelectorAll("[data-requires-origin]").forEach(function (el) {
      el.hidden = !online;
    });
    document.querySelectorAll("[data-offline-only]").forEach(function (el) {
      el.hidden = online;
    });
  }

  function paintHealth(health) {
    var online = !!(health && health.online);
    setStatusChip(
      online ? "online" : "sleeping",
      online
        ? "Game server online — Create Game and live boards available"
        : "Game server offline — leaderboard uses the last snapshot"
    );
    applyHealthVisibility(online);
  }

  function readStoredHealth() {
    try {
      var raw = sessionStorage.getItem(HEALTH_STORAGE_KEY);
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed.ts !== "number") return null;
      if (Date.now() - parsed.ts > HEALTH_FRESH_MS) return null;
      return {
        online: !!parsed.online,
        raw: parsed.raw || null,
        fromStorage: true,
      };
    } catch (_err) {
      return null;
    }
  }

  function writeStoredHealth(health) {
    try {
      sessionStorage.setItem(
        HEALTH_STORAGE_KEY,
        JSON.stringify({
          online: !!(health && health.online),
          raw: health && health.raw ? health.raw : null,
          ts: Date.now(),
        })
      );
    } catch (_err) {
      /* private mode / quota — ignore */
    }
  }

  function fetchEdgeHealthNetwork() {
    var url = HEALTH_URL + "?_=" + Date.now();
    return fetchWithTimeout(url, { cache: "no-store" }, FETCH_TIMEOUT_MS)
      .then(function (res) {
        if (!res.ok) throw new Error("health unavailable");
        return res.json();
      })
      .then(function (data) {
        var online =
          data && (data.status === "online" || data.online === true);
        healthCache = { online: online, raw: data };
        writeStoredHealth(healthCache);
        return healthCache;
      })
      .catch(function () {
        // Do not stamp offline on fetch/timeout blips — keep last good Online in memory and storage.
        if (healthCache && healthCache.online) return healthCache;
        healthCache = { online: false, raw: null };
        return healthCache;
      });
  }

  function notifyHealthUiListeners(health, meta) {
    healthUiListeners.slice().forEach(function (cb) {
      try {
        cb(health, meta || {});
      } catch (_err) {}
    });
  }

  function onHealthUi(cb) {
    if (typeof cb !== "function") return;
    healthUiListeners.push(cb);
    if (healthCache) {
      try {
        cb(healthCache, { becameOnline: false });
      } catch (_err) {}
    }
  }

  function wakeLiveSurfaces() {
    if (window.CVH.refreshGamesList) {
      window.CVH.refreshGamesList("active");
      window.CVH.refreshGamesList("completed");
    }
    if (window.CVH.refreshAttemptsList) {
      window.CVH.refreshAttemptsList("puzzles");
      window.CVH.refreshAttemptsList("identify");
    }
    if (window.CVH.refreshHumanGamesLists) {
      window.CVH.refreshHumanGamesLists();
    }
  }

  function applyHealthResult(health) {
    var online = !!(health && health.online);
    var becameOnline = online && lastPaintedOnline === false;
    paintHealth(health);
    notifyHealthUiListeners(health, { becameOnline: becameOnline });
    if (becameOnline) wakeLiveSurfaces();
    lastPaintedOnline = online;
    return health;
  }

  function tickHealthPoll() {
    return checkEdgeHealth({ force: true }).then(applyHealthResult);
  }

  function healthPollDelayMs() {
    if (healthCache && healthCache.online) return HEALTH_POLL_MS;
    return HEALTH_POLL_SLEEPING_MS;
  }

  function scheduleHealthPoll() {
    if (healthPollTimer) {
      clearTimeout(healthPollTimer);
      healthPollTimer = null;
    }
    if (!healthPollStarted) return;
    // Keep probing while Sleeping even if the tab is in the background.
    if (document.hidden && healthCache && healthCache.online) return;
    healthPollTimer = setTimeout(function () {
      healthPollTimer = null;
      tickHealthPoll()
        .catch(function () {})
        .then(function () {
          scheduleHealthPoll();
        });
    }, healthPollDelayMs());
  }

  function onHealthVisibilityChange() {
    if (document.hidden) {
      if (healthCache && healthCache.online && healthPollTimer) {
        clearTimeout(healthPollTimer);
        healthPollTimer = null;
      }
      return;
    }
    if (!healthPollStarted) return;
    tickHealthPoll()
      .catch(function () {})
      .then(function () {
        scheduleHealthPoll();
      });
  }

  function onHealthPageShow(ev) {
    if (!healthPollStarted) return;
    if (ev && ev.persisted === false) return;
    tickHealthPoll()
      .catch(function () {})
      .then(function () {
        scheduleHealthPoll();
      });
  }

  function startHealthPoll() {
    if (healthPollStarted) return;
    healthPollStarted = true;
    document.addEventListener("visibilitychange", onHealthVisibilityChange);
    window.addEventListener("pageshow", onHealthPageShow);
    scheduleHealthPoll();
  }

  function checkEdgeHealth(options) {
    options = options || {};
    if (!options.force && healthCache) {
      return Promise.resolve(healthCache);
    }
    if (!options.force && healthInflight) {
      return healthInflight;
    }
    healthInflight = fetchEdgeHealthNetwork().then(
      function (health) {
        healthInflight = null;
        return health;
      },
      function (err) {
        healthInflight = null;
        throw err;
      }
    );
    return healthInflight;
  }

  function applyHealthUi(options) {
    options = options || {};
    if (typeof options.onHealth === "function") {
      healthUiListeners.push(options.onHealth);
    }
    var stored = readStoredHealth();
    if (stored) {
      healthCache = { online: stored.online, raw: stored.raw };
      lastPaintedOnline = !!stored.online;
      paintHealth(stored);
      notifyHealthUiListeners(stored, { becameOnline: false });
    } else {
      setStatusChip(
        "checking",
        "Checking whether the game server is reachable…"
      );
    }
    if (document.querySelector("[data-status-chip]")) startHealthPoll();
    return checkEdgeHealth({ force: true }).then(applyHealthResult);
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

  /** Shared height sync for /g/, /p/, /i/ watch layouts. */
  function syncWatchHeights(options) {
    options = options || {};
    var wrap = document.getElementById(options.boardWrapId || "board-wrap");
    var track = document.getElementById(options.evalTrackId || "eval-track");
    var movesCol = document.getElementById(options.movesColId || "moves-col");
    var infoCol = document.querySelector(options.infoColSelector || ".info-col");
    var stack = document.querySelector(options.stackSelector || ".board-stack");
    if (wrap && track && wrap.offsetHeight) {
      track.style.height = wrap.offsetHeight + "px";
    }
    var ref = (stack && stack.offsetHeight) ? stack : wrap;
    if (ref && ref.offsetHeight) {
      var h = ref.offsetHeight + "px";
      if (movesCol) movesCol.style.maxHeight = h;
      if (infoCol) infoCol.style.height = h;
    }
  }

  function showWatchPollError(message) {
    var el = document.getElementById("poll-error");
    if (!el) return;
    if (message) {
      el.textContent = message;
      el.classList.add("is-visible");
    } else {
      el.textContent = "";
      el.classList.remove("is-visible");
    }
  }

  window.CVH = window.CVH || {};
  window.CVH.applyHealthUi = applyHealthUi;
  window.CVH.onHealthUi = onHealthUi;
  window.CVH.checkEdgeHealth = checkEdgeHealth;
  window.CVH.mountLeaderboardTable = mountLeaderboardTable;
  window.CVH.fetchLeaderboard = fetchLeaderboard;
  window.CVH.fetchLeaderboardSnapshot = fetchLeaderboardSnapshot;
  window.CVH.onLiveLeaderboard = onLiveLeaderboard;
  window.CVH.getLatestLiveLeaderboard = getLatestLiveLeaderboard;
  window.CVH.fetchSpecialtyLeaderboard = fetchSpecialtyLeaderboard;
  window.CVH.formatElo = formatElo;
  window.CVH.formatQualityMean = formatQualityMean;
  window.CVH.isProvisional = isProvisional;
  window.CVH.formatAgentNameCell = formatAgentNameCell;
  window.CVH.nameWithoutElo = nameWithoutElo;
  window.CVH.abbreviateListName = abbreviateListName;
  window.CVH.syncWatchHeights = syncWatchHeights;
  window.CVH.showWatchPollError = showWatchPollError;

  document.addEventListener("DOMContentLoaded", function () {
    setActiveNav();
    ensureCalibrationNav();
    ensurePuzzleSetNav();
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
    // Pages OAuth only — skip on origin operator pages to avoid /auth/me 404 noise.
    if (navPath() !== "/calibration" && navPath() !== "/puzzle-set") {
      loadScriptOnce("/js/auth.js");
    }
  });
})();
