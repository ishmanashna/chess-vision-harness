(function () {
  "use strict";

  var ENGINES_SORT_KEY = "cvh-leaderboard-engines-sort";
  var ENGINE_NUMERIC_KEYS = ["elo", "mean_accuracy", "mean_play_rating"];

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatQualityMean(value, suffix) {
    if (window.CVH && typeof window.CVH.formatQualityMean === "function") {
      return window.CVH.formatQualityMean(value, suffix);
    }
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (isNaN(n)) return "—";
    if (suffix) return String(n) + suffix;
    return String(Math.round(n));
  }

  function engineKind(row) {
    if (row.anchor) return "Anchor";
    if (row.uncalibrated) return "Uncalibrated";
    return "Calibrated";
  }

  function normalizeEngineRow(row) {
    return {
      id: row.id || "",
      name: row.name || row.id || "—",
      elo: row.elo,
      mean_accuracy: row.mean_accuracy,
      mean_play_rating: row.mean_play_rating,
      kind: engineKind(row),
      anchor: row.anchor ? 1 : 0,
      _raw: row,
    };
  }

  /** Default: floaters first, then Elo desc (legacy engines order). */
  function sortEnginesDefault(rows) {
    return rows.slice().sort(function (a, b) {
      if (a.anchor !== b.anchor) return a.anchor - b.anchor;
      return (Number(b.elo) || 0) - (Number(a.elo) || 0);
    });
  }

  function sortEngineRows(rows, key, dir) {
    var ts = window.CVH && window.CVH.tableSort;
    if (!ts || !key) return sortEnginesDefault(rows);
    return ts.sortRows(rows, key, dir, {
      numericKeys: ENGINE_NUMERIC_KEYS,
      tieKey: "id",
    });
  }

  function defaultEngineSortDir(key) {
    if (ENGINE_NUMERIC_KEYS.indexOf(key) !== -1) return "desc";
    return "asc";
  }

  function renderEngineRows(rows) {
    if (!rows.length) {
      return '<tr><td colspan="6" class="empty-state">No engine ratings on the ladder yet.</td></tr>';
    }
    return rows
      .map(function (row, index) {
        var raw = row._raw || row;
        return (
          "<tr>" +
          '<td class="rank">' +
          (index + 1) +
          "</td>" +
          "<td>" +
          escapeHtml(row.name || "—") +
          "</td>" +
          '<td class="elo">' +
          escapeHtml(raw.elo != null ? String(raw.elo) : "—") +
          "</td>" +
          "<td>" +
          escapeHtml(formatQualityMean(raw.mean_accuracy, "%")) +
          "</td>" +
          '<td title="Estimated strength from move accuracy via the calibration accuracy→Elo table — not ladder Elo.">' +
          escapeHtml(formatQualityMean(raw.mean_play_rating)) +
          "</td>" +
          "<td>" +
          escapeHtml(row.kind) +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function mountEnginesTable(container) {
    var table = container.querySelector("table");
    var tbody = container.querySelector("tbody");
    var ts = window.CVH && window.CVH.tableSort;
    var state = ts
      ? ts.loadState(
          ENGINES_SORT_KEY,
          { key: null, dir: "desc" },
          {
            estimatedElo: "mean_play_rating",
            performance: "mean_play_rating",
            accuracy: "mean_accuracy",
          }
        )
      : { key: null, dir: "desc" };
    if (state.key === "performance" || state.key === "estimatedElo") {
      state.key = "mean_play_rating";
    }
    if (state.key === "accuracy") state.key = "mean_accuracy";
    var sortKey = state.key;
    var sortDir = state.dir;
    var cache = [];

    function paint() {
      if (!tbody) return;
      tbody.innerHTML = renderEngineRows(sortEngineRows(cache, sortKey, sortDir));
      if (ts) ts.paintHeaders(table, sortKey, sortDir);
    }

    function paintOpponents(data) {
      if (!data || !tbody) return;
      var opponents = Array.isArray(data.opponents) ? data.opponents : [];
      cache = opponents.map(normalizeEngineRow);
      paint();
    }

    function paintError() {
      if (tbody) {
        tbody.innerHTML =
          '<tr><td colspan="6" class="empty-state">Could not load engine ladder.</td></tr>';
      }
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
          ts.saveState(ENGINES_SORT_KEY, sortKey, sortDir);
        },
        defaultDirForKey: defaultEngineSortDir,
        onChange: paint,
      });
    }

    var snapshotLb =
      window.CVH && window.CVH.fetchLeaderboardSnapshot
        ? window.CVH.fetchLeaderboardSnapshot
        : function () {
            return fetch("/data/leaderboard.json", { cache: "no-cache" }).then(function (
              res
            ) {
              if (!res.ok) throw new Error("leaderboard fetch failed");
              return res.json();
            });
          };

    // Live hook first so snapshot failures never skip registration.
    if (window.CVH && typeof window.CVH.onLiveLeaderboard === "function") {
      window.CVH.onLiveLeaderboard(paintOpponents);
    }

    var latest =
      window.CVH && typeof window.CVH.getLatestLiveLeaderboard === "function"
        ? window.CVH.getLatestLiveLeaderboard()
        : null;
    if (latest && latest.live) {
      paintOpponents(latest);
    } else {
      snapshotLb()
        .then(paintOpponents)
        .catch(paintError);
    }
  }

  window.CVH = window.CVH || {};
  window.CVH.mountEnginesTable = mountEnginesTable;
})();