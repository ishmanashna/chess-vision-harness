(function () {
  "use strict";

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
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return "";
      var time = pad2(d.getHours()) + ":" + pad2(d.getMinutes());
      var day = d.getDate();
      var month = pad2(d.getMonth() + 1);
      var year = String(d.getFullYear()).slice(-2);
      return time + " " + day + "/" + month + "/" + year;
    } catch (_err) {
      return "";
    }
  }

  function labelFor(entry) {
    var agent = entry.agentName || "Agent";
    var you = entry.nickname || "You";
    return you + " vs " + agent;
  }

  function renderRows(entries, registry) {
    if (!entries.length) return "";
    return entries
      .map(function (entry) {
        var href = registry.playHref(entry.gameId, entry.token);
        var when = formatWhen(entry.createdAt);
        return (
          "<li class=\"your-games-item\">" +
          '<a class="btn btn-secondary btn-sm" href="' +
          escapeHtml(href) +
          '">Resume</a> ' +
          "<span class=\"your-games-label\">" +
          escapeHtml(labelFor(entry)) +
          "</span> " +
          '<code class="your-games-id">' +
          escapeHtml(entry.gameId) +
          "</code>" +
          (when ? ' <span class="your-games-when">' + escapeHtml(when) + "</span>" : "") +
          "</li>"
        );
      })
      .join("");
  }

  function paintList(root, registry) {
    var listEl = root.querySelector("[data-human-games-list]");
    var emptyEl = root.querySelector("[data-human-games-empty]");
    if (!listEl) return;
    var entries = registry.sorted();
    listEl.innerHTML = renderRows(entries, registry);
    if (emptyEl) emptyEl.hidden = entries.length > 0;
  }

  function mountYourGamesPanel(root) {
    var registry = window.CVH && window.CVH.humanGames;
    if (!registry || !root) return;

    function refresh() {
      paintList(root, registry);
    }

    refresh();
    window.addEventListener("storage", function (ev) {
      if (ev.key === registry.STORAGE_KEY) refresh();
    });
    window.CVH.refreshHumanGamesLists = refresh;
  }

  function mountSpectatorMyGames(spectatorRoot) {
    var panel = spectatorRoot && spectatorRoot.querySelector("[data-spec-panel='mygames']");
    if (!panel) return;
    mountYourGamesPanel(panel);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var spectatorRoot = document.querySelector("[data-spectator-page]");
    if (spectatorRoot) mountSpectatorMyGames(spectatorRoot);
  });

  window.CVH = window.CVH || {};
  window.CVH.humanGamesUi = {
    paintList: paintList,
    mountYourGamesPanel: mountYourGamesPanel,
  };
})();
