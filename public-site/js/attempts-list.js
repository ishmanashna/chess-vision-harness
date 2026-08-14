/**
 * Spectator hub Puzzles and Identify tab lists.
 * Each table is fed by the public attempts APIs
 * (/api/v1/puzzles/public/attempts, /api/v1/identify/public/attempts),
 * newest first with sortable, linkable rows. Lists refresh on tab activation
 * via window.CVH.refreshAttemptsLists (wired in spectator-tabs.js).
 */

(function () {
  "use strict";

  var SORT_KEY_PREFIX = "cvh-attempts-sort-";
  var NUMERIC_SORT_KEYS = ["puzzle_rating", "accuracy", "moves", "puzzles", "startedMs"];

  var ENDPOINTS = {
    puzzles: "/api/v1/puzzles/public/attempts?limit=100",
    identify: "/api/v1/identify/public/attempts?limit=100",
  };

  var WATCH_PREFIX = { puzzles: "/p/", identify: "/i/" };

  var PUZZLE_COLSPAN = 8;
  var IDENTIFY_COLSPAN = 7;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function pad2(n) {
    return n < 10 ? "0" + n : String(n);
  }

  /** Compact local timestamp: HH:mm D/MM/YY (e.g. 22:24 1/08/26). */
  function formatWhen(iso) {
    if (!iso) return "—";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return "—";
      var time = pad2(d.getHours()) + ":" + pad2(d.getMinutes());
      var day = d.getDate();
      var month = pad2(d.getMonth() + 1);
      var year = String(d.getFullYear()).slice(-2);
      return time + " " + day + "/" + month + "/" + year;
    } catch (_err) {
      return "—";
    }
  }

  function statusLabel(row, kind) {
    if (row.status === "finished") {
      if (kind === "puzzles") return row.result === "correct" ? "Solved" : "Failed";
      return row.result === "correct" ? "Identified" : "Mismatched";
    }
    if (row.status === "abandoned") return "Abandoned";
    return "In progress";
  }

  function fmtAccuracy(value) {
    if (value == null || value === "") return "—";
    return String(Math.round(Number(value) * 100)) + "%";
  }

  function emptyText(kind) {
    if (kind === "puzzles") {
      return "No puzzle attempts yet — agents start them via the Puzzles flow on the Create Game page.";
    }
    return "No board-identification attempts yet — agents start them via the Board identification flow on the Create Game page.";
  }

  function colspanFor(kind) {
    return kind === "puzzles" ? PUZZLE_COLSPAN : IDENTIFY_COLSPAN;
  }

  function fetchPuzzleTotalsByAgent() {
    return fetch("/api/leaderboard/puzzles/live")
      .then(function (res) {
        return res.ok ? res.json() : null;
      })
      .catch(function () {
        return null;
      })
      .then(function (data) {
        var map = {};
        ((data && data.agents) || []).forEach(function (agent) {
          var key = agent.name || agent.id;
          if (key) map[key] = agent.attempts != null ? agent.attempts : 0;
        });
        return map;
      });
  }

  function normalizeAttempt(row, kind, puzzleTotals) {
    var startedMs = row.started_at ? Date.parse(row.started_at) || 0 : 0;
    var common = {
      attempt_id: row.attempt_id || "",
      agent_name: row.agent_name || "—",
      status: statusLabel(row, kind),
      statusRaw: row.status || "—",
      result: row.status === "active" ? "—" : row.result || "—",
      startedMs: startedMs,
      started: formatWhen(row.started_at),
      puzzles: 0,
    };
    if (kind === "puzzles") {
      common.puzzle_rating =
        row.puzzle_rating != null ? String(row.puzzle_rating) : "—";
      common.moves = row.moves_played != null ? String(row.moves_played) : "—";
      var total = puzzleTotals && puzzleTotals[row.agent_name];
      common.puzzles = total != null ? String(total) : "—";
    } else {
      common.accuracy = fmtAccuracy(row.accuracy);
      common.full =
        row.full_position == null ? "—" : row.full_position ? "Yes" : "No";
    }
    return common;
  }

  function renderCells(row, kind) {
    if (kind === "puzzles") {
      return (
        '<td class="quality">' +
        escapeHtml(row.puzzle_rating) +
        "</td><td>" +
        escapeHtml(row.moves) +
        "</td><td>" +
        escapeHtml(row.puzzles) +
        "</td>"
      );
    }
    return (
      '<td class="quality">' +
      escapeHtml(row.accuracy) +
      "</td><td>" +
      escapeHtml(row.full) +
      "</td>"
    );
  }

  function renderRows(rows, kind) {
    var colspan = colspanFor(kind);
    if (!rows.length) {
      return (
        '<tr><td colspan="' +
        colspan +
        '" class="empty-state">' +
        escapeHtml(emptyText(kind)) +
        "</td></tr>"
      );
    }
    return rows
      .map(function (row) {
        return (
          "<tr>" +
          '<td><a href="' +
          escapeHtml(WATCH_PREFIX[kind]) +
          escapeHtml(row.attempt_id) +
          '"><code>' +
          escapeHtml(row.attempt_id) +
          "</code></a></td>" +
          "<td>" +
          escapeHtml(row.agent_name) +
          "</td>" +
          "<td>" +
          escapeHtml(row.status) +
          "</td>" +
          "<td>" +
          escapeHtml(row.result) +
          "</td>" +
          renderCells(row, kind) +
          "<td>" +
          escapeHtml(row.started) +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function mountAttemptsList(root) {
    var kind = root.getAttribute("data-attempts-kind") || "puzzles";
    var table = root.querySelector("[data-attempts-table]");
    var tbody = table && table.querySelector("tbody");
    var storageKey = SORT_KEY_PREFIX + kind;
    var ts = window.CVH && window.CVH.tableSort;
    var state = ts
      ? ts.loadState(storageKey, { key: "startedMs", dir: "desc" })
      : { key: "startedMs", dir: "desc" };
    var sortKey = state.key || "startedMs";
    var sortDir = state.dir;
    var cache = [];

    function paint() {
      if (!tbody) return;
      tbody.innerHTML = renderRows(
        ts
          ? ts.sortRows(cache, sortKey, sortDir, {
              numericKeys: NUMERIC_SORT_KEYS,
              tieKey: "attempt_id",
            })
          : cache,
        kind
      );
      if (ts) ts.paintHeaders(table, sortKey, sortDir);
    }

    if (table && ts) {
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
        defaultDirForKey: function (key) {
          return NUMERIC_SORT_KEYS.indexOf(key) >= 0 ? "desc" : "asc";
        },
        onChange: paint,
      });
    }

    root.refreshAttempts = function () {
      if (!tbody) return;
      var attemptsReq = fetch(ENDPOINTS[kind]).then(function (res) {
        if (!res.ok) throw new Error("Could not load attempts");
        return res.json();
      });
      var totalsReq =
        kind === "puzzles" ? fetchPuzzleTotalsByAgent() : Promise.resolve(null);

      Promise.all([attemptsReq, totalsReq])
        .then(function (parts) {
          var data = parts[0];
          var puzzleTotals = parts[1];
          cache = (Array.isArray(data.attempts) ? data.attempts : []).map(function (row) {
            return normalizeAttempt(row, kind, puzzleTotals);
          });
          paint();
        })
        .catch(function () {
          cache = [];
          tbody.innerHTML =
            '<tr><td colspan="' +
            colspanFor(kind) +
            '" class="empty-state">Could not load attempts — is the server online?</td></tr>';
        });
    };
  }

  function refreshAll() {
    document.querySelectorAll("[data-attempts-list]").forEach(function (root) {
      if (root.refreshAttempts) root.refreshAttempts();
    });
  }

  window.CVH = window.CVH || {};
  window.CVH.refreshAttemptsLists = refreshAll;

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-attempts-list]").forEach(mountAttemptsList);
  });
})();
