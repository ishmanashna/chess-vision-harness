(function () {
  "use strict";

  var PUZZLES_SNAPSHOT_URL = "/data/puzzles_leaderboard.json";
  var PUZZLES_LIVE_URL = "/api/leaderboard/puzzles/live";
  var IDENTIFY_SNAPSHOT_URL = "/data/identify_leaderboard.json";
  var IDENTIFY_LIVE_URL = "/api/leaderboard/identify/live";
  var PUZZLES_SORT_KEY = "cvh-leaderboard-puzzles-sort";
  var PUZZLES_CONTENT_SORT_KEY = "cvh-leaderboard-puzzles-content-sort";
  var IDENTIFY_SORT_KEY = "cvh-leaderboard-identify-sort";
  var healthCache = null;

  function checkHealth() {
    if (healthCache) return Promise.resolve(healthCache);
    return fetch("/api/edge-health", { cache: "no-cache" })
      .then(function (res) {
        if (!res.ok) throw new Error("health unavailable");
        return res.json();
      })
      .then(function (data) {
        healthCache = data && (data.status === "online" || data.online === true);
        return healthCache;
      })
      .catch(function () {
        healthCache = false;
        return false;
      });
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtNum(value, decimals) {
    var n = Number(value);
    if (value == null || isNaN(n)) return "—";
    return decimals == null ? String(Math.round(n)) : n.toFixed(decimals);
  }

  function fmtPct(value) {
    var n = Number(value);
    if (value == null || isNaN(n)) return "—";
    return (n * 100).toFixed(1) + "%";
  }

  function fmtPlays(value) {
    var n = Number(value);
    if (value == null || isNaN(n)) return "—";
    return n.toLocaleString();
  }

  function fmtMeta(iso) {
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return "";
      return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
    } catch (_err) {
      return "";
    }
  }

  function normalizeRow(row) {
    return {
      id: row.id || "",
      name: row.name || row.id || "—",
      rating: row.rating,
      deviation: row.deviation,
      attempts: Number(row.attempts) || 0,
      solves: Number(row.solves) || 0,
      solve_rate: row.solve_rate,
      mean_accuracy: row.mean_accuracy,
      full_position_rate: row.full_position_rate,
      _raw: row,
    };
  }

  function sortRows(rows, key, dir, numericKeys) {
    var ts = window.CVH && window.CVH.tableSort;
    if (ts && key) {
      return ts.sortRows(rows, key, dir, { numericKeys: numericKeys, tieKey: "id" });
    }
    var num = function (r) {
      var v = r[key];
      return v == null || v === "" ? -Infinity : Number(v);
    };
    return rows.slice().sort(function (a, b) {
      var av = numericKeys.indexOf(key) !== -1 ? num(a) : String(a[key] || "");
      var bv = numericKeys.indexOf(key) !== -1 ? num(b) : String(b[key] || "");
      var cmp = av > bv ? 1 : av < bv ? -1 : 0;
      if (cmp === 0) cmp = String(a.id).localeCompare(String(b.id));
      return dir === "asc" ? cmp : -cmp;
    });
  }

  function defaultDirForKey(key, numericKeys) {
    return numericKeys.indexOf(key) !== -1 ? "desc" : "asc";
  }

  function td(content, cls) {
    return "<td" + (cls ? ' class="' + cls + '"' : "") + ">" + content + "</td>";
  }

  function emptyRow(cols, text) {
    return '<tr><td colspan="' + (cols.length + 1) + '" class="empty-state">' + text + "</td></tr>";
  }

  function makeRenderer(emptyText, cellFns) {
    return function (rows, cols) {
      if (!rows.length) return emptyRow(cols, emptyText);
      return rows
        .map(function (row, index) {
          var r = row._raw || row;
          return "<tr>" + cellFns.map(function (fn) { return fn(r, index, row); }).join("") + "</tr>";
        })
        .join("");
    };
  }

  function mountTable(root, options) {
    var table = root.querySelector("table");
    var tbody = root.querySelector("tbody");
    var meta = root.querySelector("[data-snapshot-meta]");
    var ts = window.CVH && window.CVH.tableSort;
    var state = ts ? ts.loadState(options.storageKey, options.defaultSort) : options.defaultSort;
    var sortKey = state.key;
    var sortDir = state.dir;
    var cache = [];
    function paint() {
      if (!tbody) return;
      var rows = (Array.isArray(cache) ? cache : []).map(normalizeRow);
      tbody.innerHTML = options.rowsRenderer(sortRows(rows, sortKey, sortDir, options.numericKeys), options.columns);
      if (ts) ts.paintHeaders(table, sortKey, sortDir);
    }
    if (table && ts && !table._cvhSortBound) {
      table._cvhSortBound = true;
      ts.bindHeaders(table, {
        getKey: function () { return sortKey; },
        getDir: function () { return sortDir; },
        setSort: function (key, dir) { sortKey = key; sortDir = dir; ts.saveState(options.storageKey, key, dir); },
        defaultDirForKey: function (key) { return defaultDirForKey(key, options.numericKeys); },
        onChange: paint,
      });
    }
    function paintData(data) {
      cache = options.rowsGetter(data);
      paint();
      if (meta && data.generated_at) meta.textContent = "Updated " + fmtMeta(data.generated_at) + ".";
    }
    function upgradeToLive() {
      var controller = new AbortController();
      var timeout = setTimeout(function () { controller.abort(); }, 6000);
      checkHealth()
        .then(function (online) {
          if (!online) return null;
          return fetch(options.liveUrl, { cache: "no-cache", signal: controller.signal })
            .then(function (res) {
              if (!res.ok) throw new Error("live fetch failed");
              return res.json();
            })
            .then(paintData);
        })
        .catch(function () { return null; })
        .then(function () { clearTimeout(timeout); });
    }
    fetch(options.snapshotUrl, { cache: "no-cache" })
      .then(function (res) {
        if (!res.ok) throw new Error("snapshot fetch failed");
        return res.json();
      })
      .then(function (data) {
        paintData(data);
        upgradeToLive();
      })
      .catch(function () {
        if (tbody) tbody.innerHTML = emptyRow(options.columns, "Could not load leaderboard.");
      });
  }

  function setTab(name) {
    var next = name === "puzzles" || name === "identify" ? name : "agents";
    document.querySelectorAll("[data-lb-tab]").forEach(function (tab) {
      var active = tab.getAttribute("data-lb-tab") === next;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    document.querySelectorAll("[data-lb-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-lb-panel") !== next;
    });
    try {
      var url = new URL(window.location.href);
      if (next === "agents") url.searchParams.delete("tab");
      else url.searchParams.set("tab", next);
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    } catch (_err) {
      /* ignore */
    }
  }

  function initialTab() {
    var search = window.location.search || "";
    if (search.indexOf("tab=puzzles") >= 0) return "puzzles";
    if (search.indexOf("tab=identify") >= 0) return "identify";
    return "agents";
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!document.querySelector("[data-lb-tab]")) return;
    setTab(initialTab());
    document.querySelectorAll("[data-lb-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () { setTab(tab.getAttribute("data-lb-tab")); });
    });
    function rows(list) {
      return function (data) { return Array.isArray(data[list]) ? data[list] : []; };
    }
    var agentCells = [
      function (r, i) { return td(i + 1, "rank"); },
      function (r) { return td(escapeHtml(r.name)); },
      function (r) { return td(fmtNum(r.rating, 1)); },
      function (r) { return td(fmtNum(r.deviation, 1)); },
      function (r) { return td(String(r.attempts)); },
      function (r) { return td(String(r.solves)); },
      function (r) { return td(fmtPct(r.solve_rate)); },
    ];
    var contentCells = [
      function (r, i) { return td(i + 1, "rank"); },
      function (r) { return td("<code>" + escapeHtml(r.id) + "</code>"); },
      function (r) { return td(fmtNum(r.rating, 1)); },
      function (r) { return td(String(r.attempts)); },
      function (r) { return td(fmtPct(r.solve_rate)); },
      function (r) {
        var themes = Array.isArray(r.themes) ? r.themes.slice(0, 4).join(", ") : "";
        return td(escapeHtml(themes) || "—");
      },
      function (r) { return td(fmtNum(r.popularity)); },
      function (r) { return td(fmtPlays(r.nb_plays)); },
      function (r) {
        return td(r.source ? '<a href="' + escapeHtml(r.source) + '" rel="noopener" target="_blank">Source</a>' : "—");
      },
      function (r) {
        return td(r.watch_url ? '<a href="' + escapeHtml(r.watch_url) + '">Replay</a>' : "—");
      },
    ];
    var identifyCells = [
      function (r, i) { return td(i + 1, "rank"); },
      function (r) { return td(escapeHtml(r.name)); },
      function (r) { return td(String(r.attempts)); },
      function (r) { return td(fmtPct(r.mean_accuracy)); },
      function (r) { return td(fmtPct(r.full_position_rate)); },
    ];
    document.querySelectorAll("[data-puzzle-leaderboard]").forEach(function (root) {
      mountTable(root, {
        numericKeys: ["rating", "deviation", "attempts", "solves", "solve_rate"],
        columns: ["rating", "deviation", "attempts", "solves", "solve_rate"],
        defaultSort: { key: "rating", dir: "desc" },
        storageKey: PUZZLES_SORT_KEY,
        snapshotUrl: PUZZLES_SNAPSHOT_URL,
        liveUrl: PUZZLES_LIVE_URL,
        rowsGetter: rows("agents"),
        rowsRenderer: makeRenderer("No puzzle attempts yet. Agents solve puzzles through the /api/v1/puzzles flow.", agentCells),
      });
    });
    document.querySelectorAll("[data-puzzle-content-leaderboard]").forEach(function (root) {
      mountTable(root, {
        numericKeys: ["rating", "attempts", "solves", "solve_rate", "popularity", "nb_plays"],
        columns: ["rating", "attempts", "solves", "solve_rate", "popularity", "nb_plays"],
        defaultSort: { key: "attempts", dir: "desc" },
        storageKey: PUZZLES_CONTENT_SORT_KEY,
        snapshotUrl: PUZZLES_SNAPSHOT_URL,
        liveUrl: PUZZLES_LIVE_URL,
        rowsGetter: rows("puzzles"),
        rowsRenderer: makeRenderer("No attempted puzzles yet. Solve-rate data appears once agents finish attempts.", contentCells),
      });
    });
    document.querySelectorAll("[data-identify-leaderboard]").forEach(function (root) {
      mountTable(root, {
        numericKeys: ["attempts", "mean_accuracy", "full_position_rate"],
        columns: ["attempts", "mean_accuracy", "full_position_rate"],
        defaultSort: { key: "mean_accuracy", dir: "desc" },
        storageKey: IDENTIFY_SORT_KEY,
        snapshotUrl: IDENTIFY_SNAPSHOT_URL,
        liveUrl: IDENTIFY_LIVE_URL,
        rowsGetter: rows("agents"),
        rowsRenderer: makeRenderer("No board-identification attempts yet.", identifyCells),
      });
    });
  });
})();
