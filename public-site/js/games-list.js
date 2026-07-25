(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatSummary(game) {
    if (game.summary) return String(game.summary);
    if (game.turn) return String(game.turn);
    if (game.result) return String(game.result);
    return game.status || "—";
  }

  function renderRows(games) {
    if (!games.length) {
      return '<tr><td colspan="4" class="empty-state">No games in this list right now.</td></tr>';
    }
    return games
      .map(function (game) {
        var id = game.game_id || "";
        var detail = formatSummary(game);
        var extra = "";
        if (game.agent_outcome) {
          extra = " · " + game.agent_outcome;
        } else if (game.result) {
          extra = " · " + game.result;
        }
        return (
          "<tr>" +
          '<td><a href="/g/' +
          escapeHtml(id) +
          '"><code>' +
          escapeHtml(id) +
          "</code></a></td>" +
          "<td>" +
          escapeHtml(detail + extra) +
          "</td>" +
          "<td>" +
          escapeHtml(game.status || "—") +
          "</td>" +
          '<td><a class="btn btn-secondary btn-sm" href="/g/' +
          escapeHtml(id) +
          '">Open</a></td>' +
          "</tr>"
        );
      })
      .join("");
  }

  function mountGamesList(root) {
    var status = root.getAttribute("data-game-status") || "in_progress";
    var queryStatus = status === "finished" ? "finished" : "in_progress";
    var table = root.querySelector("[data-games-table] tbody");
    var meta = root.querySelector("[data-games-meta]");
    var panel = root.querySelector("[data-games-live]");

    window.CVH.applyHealthUi({
      onHealth: function (health) {
        if (panel) panel.hidden = !health.online;
        if (!health.online || !table) return;

        fetch("/api/games?status=" + encodeURIComponent(queryStatus) + "&limit=100")
          .then(function (res) {
            if (!res.ok) throw new Error("Could not load games");
            return res.json();
          })
          .then(function (data) {
            var games = Array.isArray(data.games) ? data.games : [];
            table.innerHTML = renderRows(games);
            if (meta) {
              var total = typeof data.total === "number" ? data.total : games.length;
              meta.textContent =
                total === 1 ? "1 game." : total + " games (newest first).";
            }
          })
          .catch(function () {
            table.innerHTML =
              '<tr><td colspan="4" class="empty-state">Could not load live games.</td></tr>';
          });
      },
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-games-list]").forEach(mountGamesList);
  });
})();
