(function () {
  "use strict";

  var HEALTH_URL = "/api/edge-health";
  var THEME_KEY = "chess-harness-theme";
  var PROVISIONAL_HINT =
    "Provisional — K has not returned to the stable factor (24) yet. Ratings stabilize after 100 rated games.";
  var healthCache = null;

  function navPath() {
    var path = window.location.pathname.replace(/\/+$/, "") || "/";
    return path;
  }

  function setActiveNav() {
    var current = navPath();
    var map = {
      "/": "nav-home",
      "/leaderboard": "nav-leaderboard",
      "/contact": "nav-contact",
      "/create": "nav-create",
      "/human": "nav-human",
      "/spectator": "nav-spectator",
      "/active": "nav-spectator",
      "/completed": "nav-spectator",
    };
    var activeId = map[current];
    if (!activeId && current.indexOf("/g/") === 0) activeId = "nav-spectator";
    if (!activeId && current.indexOf("/play/") === 0) activeId = "nav-human";
    if (!activeId) return;
    var link = document.getElementById(activeId);
    if (link) link.classList.add("active");
  }

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark"
      ? "dark"
      : "light";
  }

  function applyTheme(theme) {
    var t = theme === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", t);
    try {
      localStorage.setItem(THEME_KEY, t);
    } catch (_err) {}
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.textContent = t === "dark" ? "Light mode" : "Dark mode";
      btn.setAttribute(
        "aria-label",
        t === "dark" ? "Switch to light mode" : "Switch to dark mode"
      );
    });
  }

  function initThemeToggle() {
    applyTheme(currentTheme());
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        applyTheme(currentTheme() === "dark" ? "light" : "dark");
      });
    });
  }

  function formatElo(agent) {
    var games = Number(agent.games) || 0;
    var elo = agent.elo;
    var provisional =
      agent.provisional === true || (agent.provisional !== false && games < 100);
    if (elo == null || elo === "") return "—";
    return provisional ? String(elo) + "*" : String(elo);
  }

  function isProvisional(agent) {
    var games = Number(agent.games) || 0;
    return agent.provisional === true || (agent.provisional !== false && games < 100);
  }

  function sortAgents(agents) {
    return agents.slice().sort(function (a, b) {
      var eloA = Number(a.elo) || 0;
      var eloB = Number(b.elo) || 0;
      if (eloB !== eloA) return eloB - eloA;
      return String(a.name || a.id).localeCompare(String(b.name || b.id));
    });
  }

  function fetchLeaderboard() {
    return fetch("/data/leaderboard.json", { cache: "no-cache" })
      .then(function (res) {
        if (!res.ok) throw new Error("leaderboard fetch failed");
        return res.json();
      })
      .then(function (data) {
        data.agents = Array.isArray(data.agents) ? data.agents : [];
        return data;
      });
  }

  function renderLeaderboardRows(agents, limit) {
    var sorted = sortAgents(agents);
    var slice = typeof limit === "number" ? sorted.slice(0, limit) : sorted;
    if (!slice.length) {
      return (
        '<tr><td colspan="5" class="empty-state">No rated agents yet. When games finish, the ladder snapshot will appear here.</td></tr>'
      );
    }
    return slice
      .map(function (agent, index) {
        var rank = index + 1;
        var name = agent.name || agent.id || "—";
        var games = Number(agent.games) || 0;
        var provisional = isProvisional(agent);
        var eloClass = provisional ? "elo provisional" : "elo";
        var titleAttr = provisional
          ? ' title="' + escapeHtml(PROVISIONAL_HINT) + '"'
          : "";
        return (
          "<tr>" +
          '<td class="rank">' +
          rank +
          "</td>" +
          "<td>" +
          escapeHtml(name) +
          "</td>" +
          '<td class="' +
          eloClass +
          '"' +
          titleAttr +
          ">" +
          escapeHtml(formatElo(agent)) +
          "</td>" +
          "<td>" +
          games +
          "</td>" +
          "<td><code>" +
          escapeHtml(agent.id || "") +
          "</code></td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatGeneratedAt(iso) {
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return "";
      return d.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
    } catch (_err) {
      return "";
    }
  }

  function mountLeaderboardTable(container, options) {
    options = options || {};
    var limit = options.limit;
    var showMeta = options.showMeta !== false;
    fetchLeaderboard()
      .then(function (data) {
        var tbody = container.querySelector("tbody");
        if (!tbody) return;
        tbody.innerHTML = renderLeaderboardRows(data.agents, limit);
        if (showMeta) {
          var meta = container.querySelector("[data-snapshot-meta]");
          if (meta) {
            var when = formatGeneratedAt(data.generated_at);
            meta.textContent = when
              ? "Snapshot from " + when + "."
              : "Leaderboard snapshot.";
          }
        }
      })
      .catch(function () {
        var tbody = container.querySelector("tbody");
        if (tbody) {
          tbody.innerHTML =
            '<tr><td colspan="5" class="empty-state">Could not load leaderboard snapshot.</td></tr>';
        }
      });
  }

  function setStatusChip(state, detail) {
    document.querySelectorAll("[data-status-chip]").forEach(function (chip) {
      chip.dataset.state = state;
      var label = chip.querySelector("[data-status-label]");
      if (label) {
        label.textContent = state === "online" ? "Online" : "Sleeping";
      }
      chip.title =
        detail ||
        (state === "online"
          ? "Game server online"
          : "Game server offline — leaderboard uses the last snapshot");
    });
  }

  function checkEdgeHealth() {
    if (healthCache) {
      return Promise.resolve(healthCache);
    }
    return fetch(HEALTH_URL, { cache: "no-cache" })
      .then(function (res) {
        if (!res.ok) throw new Error("health unavailable");
        return res.json();
      })
      .then(function (data) {
        var online =
          data &&
          (data.status === "online" ||
            data.online === true ||
            data.origin === true);
        healthCache = { online: online, raw: data };
        return healthCache;
      })
      .catch(function () {
        healthCache = { online: false, raw: null };
        return healthCache;
      });
  }

  function applyHealthUi(options) {
    options = options || {};
    return checkEdgeHealth().then(function (health) {
      var online = health.online;
      setStatusChip(
        online ? "online" : "sleeping",
        online
          ? "Game server online — Create Game and live boards available"
          : "Game server offline — leaderboard uses the last snapshot"
      );
      document.querySelectorAll("[data-requires-origin]").forEach(function (el) {
        el.hidden = !online;
      });
      document.querySelectorAll("[data-offline-only]").forEach(function (el) {
        el.hidden = online;
      });
      if (options.onHealth) options.onHealth(health);
      return health;
    });
  }

  function loadScriptOnce(src) {
    if (document.querySelector('script[src="' + src + '"]')) return;
    var script = document.createElement("script");
    script.src = src;
    document.body.appendChild(script);
  }

  window.CVH = {
    applyHealthUi: applyHealthUi,
    mountLeaderboardTable: mountLeaderboardTable,
    fetchLeaderboard: fetchLeaderboard,
    formatElo: formatElo,
    isProvisional: isProvisional,
  };

  document.addEventListener("DOMContentLoaded", function () {
    setActiveNav();
    initThemeToggle();
    if (document.querySelector("[data-status-chip]")) {
      applyHealthUi();
    }
    document.querySelectorAll("[data-leaderboard]").forEach(function (root) {
      var limitAttr = root.getAttribute("data-limit");
      var limit = limitAttr ? parseInt(limitAttr, 10) : undefined;
      mountLeaderboardTable(root, { limit: limit, showMeta: true });
    });
    if (document.querySelector("[data-engines-leaderboard]")) {
      loadScriptOnce("/js/engines.js");
    }
    loadScriptOnce("/js/auth.js");
  });
})();
