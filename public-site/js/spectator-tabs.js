(function () {
  "use strict";

  function setTab(root, name) {
    var next = name === "completed" ? "completed" : "active";
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
      if (next === "completed") url.searchParams.set("tab", "completed");
      else url.searchParams.delete("tab");
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    } catch (_err) {
      /* ignore */
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-spectator-page]");
    if (!root) return;
    var initial =
      (window.location.search || "").indexOf("tab=completed") >= 0
        ? "completed"
        : "active";
    setTab(root, initial);
    root.querySelectorAll("[data-spec-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        setTab(root, tab.getAttribute("data-spec-tab"));
      });
    });
  });
})();
