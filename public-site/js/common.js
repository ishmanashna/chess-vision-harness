(function () {
  "use strict";

  var HEALTH_URL = "/api/edge-health";
  var LIVE_LEADERBOARD_URL = "/api/leaderboard/live";
  var SNAPSHOT_LEADERBOARD_URL = "/data/leaderboard.json";
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
      "/calibration": "nav-calibration",
    };
    var activeId = map[current];
    if (!activeId && current.indexOf("/g/") === 0) activeId = "nav-spectator";
    if (!activeId && current.indexOf("/play/") === 0) activeId = "nav-human";
    if (!activeId) return;
    var link = document.getElementById(activeId);
    if (link) link.classList.add("active");
  }

  /** Localhost only: show Calibration after Leaderboard (never on Pages). */
  function isLoopbackHost() {
    var host = window.location.hostname;
    return (
      host === "127.0.0.1" ||
      host === "localhost" ||
      host === "::1" ||
      host === "[::1]"
    );
  }

  function ensureCalibrationNav() {
    if (document.getElementById("nav-calibration")) {
      if (navPath() === "/calibration") {
        document.getElementById("nav-calibration").classList.add("active");
      }
      return;
    }
    if (!isLoopbackHost()) return;
    var leaderboard = document.getElementById("nav-leaderboard");
    if (!leaderboard || !leaderboard.parentNode) return;
    var a = document.createElement("a");
    a.href = "/calibration";
    a.id = "nav-calibration";
    a.textContent = "Calibration";
    leaderboard.parentNode.insertBefore(a, leaderboard.nextSibling);
    if (navPath() === "/calibration") a.classList.add("active");
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

  function normalizeLeaderboardPayload(data, live) {
    data.agents = Array.isArray(data.agents) ? data.agents : [];
    data.opponents = Array.isArray(data.opponents) ? data.opponents : [];
    data.live = live === true;
    return data;
  }

  function fetchLeaderboard() {
    return checkEdgeHealth().then(function (health) {
      var url = health.online ? LIVE_LEADERBOARD_URL : SNAPSHOT_LEADERBOARD_URL;
      return fetch(url, { cache: "no-cache" })
        .then(function (res) {
          if (!res.ok) throw new Error("leaderboard fetch failed");
          return res.json();
        })
        .then(function (data) {
          return normalizeLeaderboardPayload(data, health.online);
        });
    });
  }

  function formatQualityMean(value, suffix) {
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (isNaN(n)) return "—";
    return suffix ? String(n) + suffix : String(n);
  }

  function renderLeaderboardRows(agents, limit, fullColumns) {
    var sorted = sortAgents(agents);
    var slice = typeof limit === "number" ? sorted.slice(0, limit) : sorted;
    var colCount = fullColumns ? 7 : 5;
    if (!slice.length) {
      return (
        '<tr><td colspan="' +
        colCount +
        '" class="empty-state">No rated agents yet. When games finish, the ladder snapshot will appear here.</td></tr>'
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
        var accCell = fullColumns
          ? "<td>" +
            escapeHtml(formatQualityMean(agent.mean_accuracy, "%")) +
            "</td>"
          : "";
        var playCell = fullColumns
          ? "<td>" + escapeHtml(formatQualityMean(agent.mean_play_rating)) + "</td>"
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
          accCell +
          playCell +
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
    var fullColumns =
      options.fullColumns === true ||
      container.hasAttribute("data-leaderboard-full");
    fetchLeaderboard()
      .then(function (data) {
        var tbody = container.querySelector("tbody");
        if (!tbody) return;
        tbody.innerHTML = renderLeaderboardRows(data.agents, limit, fullColumns);
        if (showMeta) {
          var meta = container.querySelector("[data-snapshot-meta]");
          if (meta) {
            var when = formatGeneratedAt(data.generated_at);
            if (data.live) {
              meta.textContent = when
                ? "Live ladder · updated " + when + "."
                : "Live ladder.";
            } else {
              meta.textContent = when
                ? "Snapshot from " + when + "."
                : "Leaderboard snapshot.";
            }
          }
        }
      })
      .catch(function () {
        var tbody = container.querySelector("tbody");
        if (tbody) {
          var colCount = fullColumns ? 7 : 5;
          tbody.innerHTML =
            '<tr><td colspan="' +
            colCount +
            '" class="empty-state">Could not load leaderboard snapshot.</td></tr>';
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
    ensureCalibrationNav();
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
    // Pages OAuth only — skip on origin calibration to avoid /auth/me 404 noise.
    if (navPath() !== "/calibration") {
      loadScriptOnce("/js/auth.js");
    }
  });
})();
