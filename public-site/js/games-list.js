(function () {
  "use strict";

  var SORT_KEY = "cvh-games-sort";

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function outcomeLabel(game) {
    if (game.outcome_label) return String(game.outcome_label);
    var o = game.agent_outcome;
    if (o && typeof o === "object" && o.label) return String(o.label);
    if (typeof o === "string") return o;
    if (game.result) return String(game.result);
    return "";
  }

  function formatWhen(iso) {
    if (!iso) return "—";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return "—";
      return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
    } catch (_err) {
      return "—";
    }
  }

  function normalizeGame(game) {
    return {
      id: game.game_id || "",
      agent: game.model_name || game.model_id || "—",
      modelId: game.model_id || "",
      agentElo: game.agent_elo != null ? Number(game.agent_elo) : null,
      opponent: game.opponent_label || game.opponent_id || "—",
      opponentElo: game.opponent_elo != null ? Number(game.opponent_elo) : null,
      result: game.turn || outcomeLabel(game) || game.status || "—",
      status: game.status || "—",
      when: game.last_activity || "",
      whenMs: game.last_activity ? Date.parse(game.last_activity) || 0 : 0,
    };
  }

  function sortGames(rows, key, dir) {
    var mult = dir === "asc" ? 1 : -1;
    return rows.slice().sort(function (a, b) {
      var va;
      var vb;
      if (key === "agentElo" || key === "opponentElo" || key === "whenMs") {
        va = a[key] == null ? -Infinity : a[key];
        vb = b[key] == null ? -Infinity : b[key];
        if (va !== vb) return va < vb ? -mult : mult;
      } else {
        va = String(a[key] || "").toLowerCase();
        vb = String(b[key] || "").toLowerCase();
        if (va !== vb) return va < vb ? -mult : mult;
      }
      return String(a.id).localeCompare(String(b.id)) * mult;
    });
  }

  function renderRows(rows) {
    if (!rows.length) {
      return '<tr><td colspan="7" class="empty-state">No games in this list right now.</td></tr>';
    }
    return rows
      .map(function (g) {
        var elo =
          g.agentElo != null ? escapeHtml(String(g.agentElo)) : "—";
        return (
          "<tr>" +
          '<td><a href="/g/' +
          escapeHtml(g.id) +
          '"><code>' +
          escapeHtml(g.id) +
          "</code></a></td>" +
          "<td>" +
          escapeHtml(g.agent) +
          "</td>" +
          '<td class="elo">' +
          elo +
          "</td>" +
          "<td>" +
          escapeHtml(g.opponent) +
          "</td>" +
          "<td>" +
          escapeHtml(g.result) +
          "</td>" +
          "<td>" +
          escapeHtml(formatWhen(g.when)) +
          "</td>" +
          '<td><a class="btn btn-secondary btn-sm" href="/g/' +
          escapeHtml(g.id) +
          '">Open</a></td>' +
          "</tr>"
        );
      })
      .join("");
  }

  function mountGamesList(root) {
    var status = root.getAttribute("data-game-status") || "in_progress";
    var queryStatus = status === "finished" ? "finished" : "in_progress";
    var table = root.querySelector("[data-games-table]");
    var tbody = table && table.querySelector("tbody");
    var meta = root.querySelector("[data-games-meta]");
    var panel = root.querySelector("[data-games-live]");
    var sortKey = "whenMs";
    var sortDir = "desc";
    var cache = [];

    try {
      var saved = JSON.parse(localStorage.getItem(SORT_KEY + "-" + queryStatus) || "null");
      if (saved && saved.key) {
        sortKey = saved.key;
        sortDir = saved.dir === "asc" ? "asc" : "desc";
      }
    } catch (_err) {}

    function paint() {
      if (!tbody) return;
      tbody.innerHTML = renderRows(sortGames(cache, sortKey, sortDir));
      if (!table) return;
      table.querySelectorAll("[data-sort]").forEach(function (th) {
        var key = th.getAttribute("data-sort");
        th.setAttribute("aria-sort", key === sortKey ? (sortDir === "asc" ? "ascending" : "descending") : "none");
        th.classList.toggle("is-sorted", key === sortKey);
      });
    }

    if (table) {
      table.querySelectorAll("[data-sort]").forEach(function (th) {
        th.style.cursor = "pointer";
        th.addEventListener("click", function () {
          var key = th.getAttribute("data-sort");
          if (!key) return;
          if (sortKey === key) {
            sortDir = sortDir === "asc" ? "desc" : "asc";
          } else {
            sortKey = key;
            sortDir = key === "whenMs" || key === "agentElo" ? "desc" : "asc";
          }
          try {
            localStorage.setItem(
              SORT_KEY + "-" + queryStatus,
              JSON.stringify({ key: sortKey, dir: sortDir })
            );
          } catch (_err) {}
          paint();
        });
      });
    }

    window.CVH.applyHealthUi({
      onHealth: function (health) {
        if (panel) panel.hidden = !health.online;
        if (!health.online || !tbody) return;

        fetch("/api/games?status=" + encodeURIComponent(queryStatus) + "&limit=100")
          .then(function (res) {
            if (!res.ok) throw new Error("Could not load games");
            return res.json();
          })
          .then(function (data) {
            var games = Array.isArray(data.games) ? data.games : [];
            cache = games.map(normalizeGame);
            paint();
            if (meta) {
              meta.textContent = "";
              meta.hidden = true;
            }
          })
          .catch(function () {
            tbody.innerHTML =
              '<tr><td colspan="7" class="empty-state">Could not load live games.</td></tr>';
          });
      },
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-games-list]").forEach(mountGamesList);
  });
})();
