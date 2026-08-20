(function () {

  "use strict";



  var SORT_KEY = "cvh-games-sort";

  var SORT_MIGRATE = { estimatedElo: "performance" };

  var NUMERIC_SORT_KEYS = ["whiteElo", "blackElo", "whenMs", "accuracy", "performance"];



  function escapeHtml(value) {

    return String(value)

      .replace(/&/g, "&amp;")

      .replace(/</g, "&lt;")

      .replace(/>/g, "&gt;")

      .replace(/"/g, "&quot;");

  }



  function isListTimeout(game) {

    if (game.end_reason === "inactivity") return true;

    if (game.result === "*" || game.turn === "*") return true;

    var label = String(game.end_reason_label || game.turn || "");

    return /idle timeout/i.test(label);

  }



  function outcomeLabel(game) {

    if (isListTimeout(game)) return "Timeout";

    if (game.outcome_label) return String(game.outcome_label);

    var o = game.agent_outcome;

    if (o && typeof o === "object" && o.label) return String(o.label);

    if (typeof o === "string") return o;

    if (game.result) return String(game.result);

    return "";

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

    var white = abbreviateListName(

      game.white_display_name || game.model_name || game.model_id || "—"

    );

    var black = abbreviateListName(

      game.black_display_name || game.opponent_label || game.opponent_id || "—"

    );

    var whiteObs = avaa
      ? game.white_observation
      : human || game.game_type === "agent_vs_engine"
        ? game.agent_color === "WHITE"
          ? game.observation
          : null
        : game.agent_color === "WHITE"
          ? game.observation
          : null;
    var blackObs = avaa
      ? game.black_observation
      : human || game.game_type === "agent_vs_engine"
        ? game.agent_color === "BLACK"
          ? game.observation
          : null
        : game.agent_color === "BLACK"
          ? game.observation
          : null;

    return {

      id: game.game_id || "",

      gameType: game.game_type || "",

      mode: modeLabel(game.game_type || "agent_vs_engine").short,

      isAvaa: avaa,

      isHuman: human,

      white: white,

      whiteObservation: whiteObs,

      whiteElo: game.white_elo != null ? Number(game.white_elo) : null,

      black: black,

      blackObservation: blackObs,

      blackElo: game.black_elo != null ? Number(game.black_elo) : null,

      accuracy: qualityPair(game, "accuracy"),

      performance: qualityPair(game, "play_rating"),

      result: resultLabel(game),

      status: game.status || "—",

      when: game.last_activity || "",

      whenMs: game.last_activity ? Date.parse(game.last_activity) || 0 : 0,

    };

  }



  function nameWithoutElo(value) {

    return window.CVH.nameWithoutElo(value);

  }



  function abbreviateListName(value) {

    return window.CVH.abbreviateListName(value);

  }



  function formatAccuracy(value) {

    return value == null || value === "" ? "—" : String(value) + "%";

  }



  function formatEstimatedElo(value) {

    return value == null || value === "" ? "—" : String(Math.round(Number(value)));

  }



  function hasQualityValue(value) {

    return value != null && value !== "";

  }



  function qualityPair(game, field) {

    var formatter = field === "accuracy" ? formatAccuracy : formatEstimatedElo;

    var white = game["white_" + field];

    var black = game["black_" + field];

    var hasWhite = hasQualityValue(white);

    var hasBlack = hasQualityValue(black);

    if (hasWhite && hasBlack) {

      return formatter(white) + " / " + formatter(black);

    }

    if (hasWhite) return formatter(white);

    if (hasBlack) return formatter(black);

    var agent = game["agent_" + field];

    return formatter(agent);

  }



  function resultLabel(game) {

    if (isListTimeout(game)) return "Timeout";

    if (game.turn) return String(game.turn);

    return outcomeLabel(game) || game.status || "—";

  }



  function sortGames(rows, key, dir) {

    var ts = window.CVH && window.CVH.tableSort;

    if (!ts) {

      return rows.slice();

    }

    return ts.sortRows(rows, key, dir, {

      numericKeys: NUMERIC_SORT_KEYS,

      tieKey: "id",

    });

  }



  function defaultDirForKey(key) {

    if (key === "whenMs" || key === "whiteElo" || key === "blackElo") return "desc";

    if (key === "accuracy" || key === "performance") return "desc";

    return "asc";

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

          (window.CVH.formatAgentNameCell
            ? window.CVH.formatAgentNameCell(g.white, g.whiteObservation)
            : escapeHtml(g.white)) +

          "</td>" +

          '<td class="elo">' +

          whiteElo +

          "</td>" +

          "<td>" +

          (window.CVH.formatAgentNameCell
            ? window.CVH.formatAgentNameCell(g.black, g.blackObservation)
            : escapeHtml(g.black)) +

          "</td>" +

          '<td class="elo">' +

          blackElo +

          "</td>" +

          '<td class="quality">' +

          escapeHtml(g.accuracy) +

          "</td>" +

          '<td class="quality">' +

          escapeHtml(g.performance) +

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

    var storageKey = SORT_KEY + "-" + queryStatus;

    var ts = window.CVH && window.CVH.tableSort;

    var state = ts

      ? ts.loadState(storageKey, { key: "whenMs", dir: "desc" }, SORT_MIGRATE)

      : { key: "whenMs", dir: "desc" };

    var sortKey = state.key || "whenMs";

    var sortDir = state.dir;

    var cache = [];



    // Persist migrated key so old estimatedElo does not linger.

    if (ts && state.key === "performance") {

      ts.saveState(storageKey, sortKey, sortDir);

    }



    function paint() {

      if (!tbody) return;

      tbody.innerHTML = renderRows(sortGames(cache, sortKey, sortDir));

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

        defaultDirForKey: defaultDirForKey,

        onChange: paint,

      });

    }



    root.refreshGames = function () {

      var healthFn =
        window.CVH && window.CVH.checkEdgeHealth
          ? window.CVH.checkEdgeHealth
          : function () {
              return Promise.resolve({ online: true });
            };

      healthFn().then(function (health) {

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

      });

    };

  }



  function refreshGamesList(panelName) {

    var root = document.querySelector(

      '[data-spec-panel="' + panelName + '"][data-games-list]'

    );

    if (root && root.refreshGames) root.refreshGames();

  }



  window.CVH = window.CVH || {};

  window.CVH.refreshGamesList = refreshGamesList;



  document.addEventListener("DOMContentLoaded", function () {

    document.querySelectorAll("[data-games-list]").forEach(mountGamesList);

  });

})();


