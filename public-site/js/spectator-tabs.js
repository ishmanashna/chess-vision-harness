(function () {
  "use strict";

  function isLoopbackHost() {
    var host = window.location.hostname;
    return (
      host === "127.0.0.1" ||
      host === "localhost" ||
      host === "::1" ||
      host === "[::1]"
    );
  }

  function normalizeTab(name) {
    if (name === "completed" || name === "mygames") return name;
    if (name === "puzzles" || name === "identify") return name;
    return "active";
  }

  function setTab(root, name) {
    var next = normalizeTab(name);
    if (isLoopbackHost() && (next === "puzzles" || next === "identify")) {
      window.location.assign("/puzzle-set");
      return;
    }
    root.querySelectorAll("[data-spec-tab]").forEach(function (tab) {
      var active = tab.getAttribute("data-spec-tab") === next;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    root.querySelectorAll("[data-spec-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-spec-panel") !== next;
    });
    try {
      var url = new URL(window.location.href);
      if (next === "active") url.searchParams.delete("tab");
      else url.searchParams.set("tab", next);
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    } catch (_err) {
      /* ignore */
    }
    if (next === "mygames" && window.CVH && window.CVH.refreshHumanGamesLists) {
      window.CVH.refreshHumanGamesLists();
    }
    if (
      (next === "active" || next === "completed") &&
      window.CVH &&
      window.CVH.refreshGamesList
    ) {
      window.CVH.refreshGamesList(next);
    }
    if (
      (next === "puzzles" || next === "identify") &&
      window.CVH &&
      window.CVH.refreshAttemptsList
    ) {
      window.CVH.refreshAttemptsList(next);
    }
  }

  function initialTab() {
    var search = window.location.search || "";
    if (search.indexOf("tab=mygames") >= 0) return "mygames";
    if (search.indexOf("tab=completed") >= 0) return "completed";
    if (search.indexOf("tab=puzzles") >= 0) return "puzzles";
    if (search.indexOf("tab=identify") >= 0) return "identify";
    return "active";
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-spectator-page]");
    if (!root) return;
    var initial = initialTab();
    if (isLoopbackHost() && (initial === "puzzles" || initial === "identify")) {
      window.location.replace("/puzzle-set");
      return;
    }
    setTab(root, initial);
    root.querySelectorAll("[data-spec-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        setTab(root, tab.getAttribute("data-spec-tab"));
      });
    });
  });
})();