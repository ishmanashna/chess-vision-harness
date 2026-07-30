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
    if (game.result === "*") return String(game.end_reason_label || "No result");
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

  function modeLabel(gameType) {
    if (gameType === "agent_vs_agent") return { short: "AvA", cls: "avaa", title: "Agent vs agent" };
    if (gameType === "human_vs_agent") {
      return { short: "AvH", cls: "avh", title: "Agent vs human (unranked)" };
    }
    return { short: "AvE", cls: "ave", title: "Agent vs engine" };
  }

  function normalizeGame(game) {
    var avaa = game.game_type === "agent_vs_agent";
    var human = game.game_type === "human_vs_agent";
    var white = nameWithoutElo(game.white_display_name || game.model_name || game.model_id || "—");
    var black = nameWithoutElo(game.black_display_name || game.opponent_label || game.opponent_id || "—");
    return {
      id: game.game_id || "",
      gameType: game.game_type || "",
      mode: modeLabel(game.game_type || "agent_vs_engine").short,
      isAvaa: avaa,
      isHuman: human,
      white: white,
      whiteElo: game.white_elo != null ? Number(game.white_elo) : null,
      black: black,
      blackElo: game.black_elo != null ? Number(game.black_elo) : null,
      accuracy: qualityPair(game, "accuracy"),
      estimatedElo: qualityPair(game, "play_rating"),
      result: resultLabel(game),
      status: game.status || "—",
      when: game.last_activity || "",
      whenMs: game.last_activity ? Date.parse(game.last_activity) || 0 : 0,
    };
  }

  function nameWithoutElo(value) {
    return String(value || "").replace(/\s*\(\d+\)\s*$/, "").trim();
  }

  function formatAccuracy(value) {
    return value == null || value === "" ? "—" : String(value) + "%";
  }

  function formatEstimatedElo(value) {
    return value == null || value === "" ? "—" : String(Math.round(Number(value)));
  }

  function qualityPair(game, field) {
    var formatter = field === "accuracy" ? formatAccuracy : formatEstimatedElo;
    var white = game["white_" + field];
    var black = game["black_" + field];
    if (white != null || black != null) {
      return formatter(white) + " / " + formatter(black);
    }
    var agent = game["agent_" + field];
    return formatter(agent);
  }

  function resultLabel(game) {
    if (game.turn === "*") return String(game.end_reason_label || "No result");
    if (game.result === "*") return String(game.end_reason_label || "No result");
    if (game.turn) return String(game.turn);
    return outcomeLabel(game) || game.status || "—";
  }

  function sortGames(rows, key, dir) {
    var mult = dir === "asc" ? 1 : -1;
    return rows.slice().sort(function (a, b) {
      var va;
      var vb;
      if (key === "whiteElo" || key === "blackElo" || key === "whenMs") {
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
      return '<tr><td colspan="10" class="empty-state">No games in this list right now.</td></tr>';
    }
    return rows
      .map(function (g) {
        var whiteElo = g.whiteElo != null ? escapeHtml(String(g.whiteElo)) : "—";
        var blackElo = g.blackElo != null ? escapeHtml(String(g.blackElo)) : "—";
        var mode = modeLabel(g.gameType || (g.isAvaa ? "agent_vs_agent" : g.isHuman ? "human_vs_agent" : "agent_vs_engine"));
        var modeBadge =
          '<span class="tag ' +
          mode.cls +
          '" title="' +
          escapeHtml(mode.title) +
          '">' +
          escapeHtml(mode.short) +
          "</span>";
        return (
          "<tr>" +
          '<td><a href="/g/' +
          escapeHtml(g.id) +
          '"><code>' +
          escapeHtml(g.id) +
          "</code></a></td>" +
          "<td>" +
          modeBadge +
          "</td>" +
          "<td>" +
          escapeHtml(g.white) +
          "</td>" +
          '<td class="elo">' +
          whiteElo +
          "</td>" +
          "<td>" +
          escapeHtml(g.black) +
          "</td>" +
          '<td class="elo">' +
          blackElo +
          "</td>" +
          '<td class="quality">' +
          escapeHtml(g.accuracy) +
          "</td>" +
          '<td class="elo quality">' +
          escapeHtml(g.estimatedElo) +
          "</td>" +
          "<td>" +
          escapeHtml(g.result) +
          "</td>" +
          "<td>" +
          escapeHtml(formatWhen(g.when)) +
          "</td>" +
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
            sortDir = key === "whenMs" || key === "whiteElo" || key === "blackElo" ? "desc" : "asc";
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
              '<tr><td colspan="10" class="empty-state">Could not load live games.</td></tr>';
          });
      },
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-games-list]").forEach(mountGamesList);
  });
})();
