/**
 * Localhost operator panel — polls GET /api/ops/snapshot every 10s.
 */
(function () {
  "use strict";

  var POLL_MS = 10000;
  var GO_ONLINE_POLL_MS = 2000;
  var LOOPBACK_HEADERS = {};
  var TAB_COPY = {
    overview: ["Overview", "Live snapshot from this PC · polls every 10s"],
    traffic: ["Traffic", "Origin requests on this PC · site visitors from Umami (Pages host)"],
    errors: ["Errors", "5xx and unexpected 4xx · in-memory ring"],
    machine: ["Machine", "Disk, processes, and local health"],
    inbox: ["Inbox", "Public Contact tab messages on this PC"],
    activity: ["Activity", "Live games, attempts, and audit tail"],
  };

  function root() {
    return document.querySelector("[data-ops-panel]");
  }

  function fmtBytes(n) {
    if (n == null || isNaN(n)) return "—";
    var units = ["B", "KB", "MB", "GB", "TB"];
    var v = Number(n);
    var i = 0;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i += 1;
    }
    return (i === 0 ? v.toFixed(0) : v.toFixed(1)) + " " + units[i];
  }

  function fmtPct(free, total) {
    if (!total) return "—";
    return Math.round((free / total) * 100) + "%";
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch (_e) {
      return iso;
    }
  }

  function shortId(id) {
    if (!id || id.length < 12) return id || "—";
    return id.slice(0, 8) + "…";
  }

  function setHidden(sel, hidden) {
    var el = root() && root().querySelector(sel);
    if (el) el.hidden = hidden;
  }

  function setDisabled(sel, disabled) {
    var el = root() && root().querySelector(sel);
    if (el) el.disabled = disabled;
  }

  var goOnlinePollTimer = null;

  function renderGoOnlineJob(job) {
    job = job || {};
    var status = job.status || "idle";
    var showPanel = status === "running" || status === "ok" || status === "fail";
    setHidden("[data-ops-go-online-panel]", !showPanel);
    setText("[data-ops-go-online-phase]", job.phase || (status === "running" ? "Running…" : ""));
    var logEl = root() && root().querySelector("[data-ops-go-online-log]");
    if (logEl) {
      var tail = job.log_tail || [];
      logEl.textContent = tail.length ? tail.join("\n") : "";
    }
    setDisabled("[data-ops-go-online]", status === "running");
    if (status === "ok" && window.CVH && typeof window.CVH.checkEdgeHealth === "function") {
      window.CVH.checkEdgeHealth({ force: true });
    }
  }

  function pollGoOnlineJob() {
    return fetch("/api/ops/go-online", {
      headers: LOOPBACK_HEADERS,
      cache: "no-store",
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Go Online status HTTP " + res.status);
        return res.json();
      })
      .then(function (job) {
        renderGoOnlineJob(job);
        if (job.status === "running") {
          if (!goOnlinePollTimer) {
            goOnlinePollTimer = setInterval(pollGoOnlineJob, GO_ONLINE_POLL_MS);
          }
        } else if (goOnlinePollTimer) {
          clearInterval(goOnlinePollTimer);
          goOnlinePollTimer = null;
        }
        if (job.status === "fail") {
          showError("Go Online failed — see log below.");
        }
        return job;
      })
      .catch(function (err) {
        if (goOnlinePollTimer) {
          clearInterval(goOnlinePollTimer);
          goOnlinePollTimer = null;
        }
        showError(err && err.message ? err.message : "Could not read Go Online status");
      });
  }

  function startGoOnlineJob() {
    setDisabled("[data-ops-go-online]", true);
    showError("");
    fetch("/api/ops/go-online", {
      method: "POST",
      headers: LOOPBACK_HEADERS,
    })
      .then(function (res) {
        if (res.status === 409) {
          return res.json().then(function (body) {
            throw new Error((body && body.detail) || "Go Online already running");
          });
        }
        if (!res.ok) throw new Error("Go Online HTTP " + res.status);
        return res.json();
      })
      .then(function () {
        setHidden("[data-ops-go-online-panel]", false);
        return pollGoOnlineJob();
      })
      .catch(function (err) {
        setDisabled("[data-ops-go-online]", false);
        showError(err && err.message ? err.message : "Could not start Go Online");
      });
  }

  function sleepPublic() {
    showError("");
    fetch("/api/ops/sleep-public", {
      method: "POST",
      headers: LOOPBACK_HEADERS,
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Sleep public HTTP " + res.status);
        return res.json();
      })
      .then(function () {
        if (window.CVH && typeof window.CVH.checkEdgeHealth === "function") {
          window.CVH.checkEdgeHealth({ force: true });
        }
        return refresh();
      })
      .catch(function (err) {
        showError(err && err.message ? err.message : "Could not sleep public site");
      });
  }

  function initGoOnlineControls() {
    var panel = root();
    if (!panel) return;
    var goBtn = panel.querySelector("[data-ops-go-online]");
    if (goBtn) {
      goBtn.addEventListener("click", startGoOnlineJob);
    }
    var sleepBtn = panel.querySelector("[data-ops-sleep-public]");
    if (sleepBtn) {
      sleepBtn.addEventListener("click", sleepPublic);
    }
    pollGoOnlineJob();
  }

  function setText(sel, text) {
    var el = root() && root().querySelector(sel);
    if (el) el.textContent = text;
  }

  function setHtml(sel, html) {
    var el = root() && root().querySelector(sel);
    if (el) el.innerHTML = html;
  }

  function showError(msg) {
    var el = root() && root().querySelector("[data-ops-error]");
    if (!el) return;
    if (msg) {
      el.textContent = msg;
      el.hidden = false;
    } else {
      el.textContent = "";
      el.hidden = true;
    }
  }

  function renderInboxList(containerSel, messages, interactive) {
    var el = root() && root().querySelector(containerSel);
    if (!el) return;
    el.innerHTML = "";
    if (!messages || !messages.length) {
      el.innerHTML = '<p class="snapshot-meta">No messages yet.</p>';
      return;
    }
    messages.forEach(function (row) {
      var article = document.createElement("article");
      article.className = "ops-mail" + (row.read ? "" : " is-unread");
      article.innerHTML =
        '<header><strong></strong><span></span></header><p></p>' +
        (interactive
          ? '<div class="ops-mail-actions"><button type="button" data-read>Mark read</button><button type="button" data-delete>Delete</button></div>'
          : "");
      article.querySelector("strong").textContent = row.sender || "Unknown";
      article.querySelector("span").textContent = fmtTime(row.created_at);
      article.querySelector("p").textContent = row.message || "";
      if (interactive) {
        article.querySelector("[data-read]").addEventListener("click", function () {
          fetch("/api/contact/inbox/" + encodeURIComponent(row.id) + "/read", {
            method: "POST",
            headers: LOOPBACK_HEADERS,
          }).then(function () {
            refresh();
          });
        });
        article.querySelector("[data-delete]").addEventListener("click", function () {
          fetch("/api/contact/inbox/" + encodeURIComponent(row.id), {
            method: "DELETE",
            headers: LOOPBACK_HEADERS,
          }).then(function () {
            refresh();
          });
        });
      }
      el.appendChild(article);
    });
  }

  function renderLiveGames(games, total) {
    var body = root() && root().querySelector("[data-live-games-body]");
    if (!body) return;
    body.innerHTML = "";
    if (!games || !games.length) {
      body.innerHTML = '<tr><td colspan="3">No games in progress.</td></tr>';
    } else {
      games.forEach(function (game) {
        var tr = document.createElement("tr");
        var mode = game.game_type || game.summary || "Game";
        tr.innerHTML =
          "<td></td><td></td><td><a></a></td>";
        tr.children[0].textContent = game.model_name || game.model_id || "Agent";
        tr.children[1].textContent = mode;
        var link = tr.querySelector("a");
        link.href = "/g/" + encodeURIComponent(game.game_id);
        link.textContent = shortId(game.game_id);
        body.appendChild(tr);
      });
    }
    setText("[data-live-games-meta]", total + " in progress");
    setText("[data-traffic-live-games]", String(total || 0));
  }

  function renderLiveAttempts(puzzles, identify) {
    var body = root() && root().querySelector("[data-live-attempts-body]");
    if (!body) return;
    body.innerHTML = "";
    var rows = [];
    (puzzles || []).forEach(function (row) {
      rows.push({
        agent: row.agent_name || row.model_id || "Agent",
        task: "Puzzle",
        url: row.watch_url || ("/p/" + row.attempt_id),
        id: row.attempt_id,
      });
    });
    (identify || []).forEach(function (row) {
      rows.push({
        agent: row.agent_name || row.model_id || "Agent",
        task: "Identify",
        url: row.watch_url || ("/i/" + row.attempt_id),
        id: row.attempt_id,
      });
    });
    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="3">No active puzzle or identify attempts.</td></tr>';
    } else {
      rows.forEach(function (row) {
        var tr = document.createElement("tr");
        tr.innerHTML = "<td></td><td></td><td><a></a></td>";
        tr.children[0].textContent = row.agent;
        tr.children[1].textContent = row.task;
        var link = tr.querySelector("a");
        link.href = row.url;
        link.textContent = shortId(row.id);
        body.appendChild(tr);
      });
    }
    setText("[data-traffic-attempts]", String(rows.length));
  }

  function renderBarChart(containerSel, buckets, valueKey, options) {
    options = options || {};
    var el = root() && root().querySelector(containerSel);
    if (!el) return;
    el.innerHTML = "";
    if (!buckets || !buckets.length) {
      el.innerHTML = '<p class="snapshot-meta">No requests yet.</p>';
      return;
    }
    var slice = buckets;
    var maxBars = options.maxBars || 120;
    if (slice.length > maxBars) {
      slice = slice.slice(slice.length - maxBars);
    }
    var peak = 1;
    slice.forEach(function (row) {
      var v = Number(row[valueKey] || 0);
      if (v > peak) peak = v;
    });
    var wrap = document.createElement("div");
    wrap.className = "ops-chart-bars";
    slice.forEach(function (row) {
      var v = Number(row[valueKey] || 0);
      var bar = document.createElement("span");
      bar.className = "ops-chart-bar" + (v > 0 ? " has-value" : "");
      bar.style.height = Math.max(2, Math.round((v / peak) * 100)) + "%";
      if (valueKey === "outage_errors") {
        bar.title = (row.minute || "") + " · " + v + " outage";
      } else {
        bar.title = (row.minute || "") + " · " + v + " req";
      }
      wrap.appendChild(bar);
    });
    el.appendChild(wrap);
  }

  function renderRouteTable(routes) {
    var body = root() && root().querySelector("[data-route-table-body]");
    if (!body) return;
    body.innerHTML = "";
    (routes || []).forEach(function (row) {
      var tr = document.createElement("tr");
      tr.innerHTML = "<td></td><td></td>";
      tr.children[0].textContent = row.family || "other";
      tr.children[1].textContent = String(row.requests != null ? row.requests : 0);
      body.appendChild(tr);
    });
  }

  function renderErrorEvents(events) {
    var el = root() && root().querySelector("[data-error-events]");
    if (!el) return;
    el.innerHTML = "";
    if (!events || !events.length) {
      el.innerHTML = '<p class="snapshot-meta">No outage events in the ring.</p>';
      return;
    }
    events.forEach(function (row) {
      var item = document.createElement("div");
      item.className = "ops-error-item";
      item.innerHTML =
        "<div class='ops-error-head'><strong></strong><span></span></div><div class='ops-error-path'></div>";
      item.querySelector("strong").textContent =
        String(row.status) + " · " + (row.kind || "error");
      item.querySelector("span").textContent = fmtTime(row.at);
      item.querySelector(".ops-error-path").textContent =
        (row.method || "GET") + " " + (row.path || "") + " · " + (row.route_family || "");
      el.appendChild(item);
    });
  }

  function renderMetricsTable(bodySel, rows, nameKey, emptyText) {
    var body = root() && root().querySelector(bodySel);
    if (!body) return;
    body.innerHTML = "";
    if (!rows || !rows.length) {
      body.innerHTML = '<tr><td colspan="2">' + (emptyText || "No data yet.") + "</td></tr>";
      return;
    }
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.innerHTML = "<td></td><td></td>";
      tr.children[0].textContent = row[nameKey] != null ? row[nameKey] : row.name || "—";
      tr.children[1].textContent = String(row.visitors != null ? row.visitors : 0);
      body.appendChild(tr);
    });
  }

  function renderAudience(audience) {
    audience = audience || {};
    var emptyEl = root() && root().querySelector("[data-audience-empty]");
    var loadedEl = root() && root().querySelector("[data-audience-loaded]");
    var configured = audience.configured === true && audience.ok !== false;
    var hasNumbers =
      configured &&
      (audience.visitors != null || audience.pageviews != null);

    if (emptyEl) {
      if (!configured || !hasNumbers) {
        emptyEl.textContent =
          audience.message ||
          "Set the Umami API token and website id in the game PC serve environment.";
        emptyEl.hidden = false;
      } else {
        emptyEl.textContent = "";
        emptyEl.hidden = true;
      }
    }
    if (loadedEl) {
      loadedEl.hidden = !hasNumbers;
    }

    var visitors = hasNumbers && audience.visitors != null ? String(audience.visitors) : "—";
    var pageviews = hasNumbers && audience.pageviews != null ? String(audience.pageviews) : "—";
    setText("[data-traffic-visitors]", visitors);
    setText("[data-traffic-pageviews]", pageviews);
    setText("[data-audience-visitors]", visitors);
    setText("[data-audience-pageviews]", pageviews);

    if (!hasNumbers) {
      renderMetricsTable("[data-audience-referrers]", [], "name");
      renderMetricsTable("[data-audience-pages]", [], "path");
      renderMetricsTable("[data-audience-countries]", [], "code");
      return;
    }

    renderMetricsTable("[data-audience-referrers]", audience.referrers || [], "name", "No referrers yet.");
    renderMetricsTable("[data-audience-pages]", audience.pages || [], "path", "No page data yet.");
    renderMetricsTable(
      "[data-audience-countries]",
      audience.countries || [],
      "code",
      "No country data yet."
    );
  }

  function fetchAudience() {
    return fetch("/api/ops/audience", {
      headers: LOOPBACK_HEADERS,
      cache: "no-store",
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Audience HTTP " + res.status);
        return res.json();
      })
      .then(function (body) {
        renderAudience(body);
        return body;
      })
      .catch(function () {
        renderAudience({
          configured: false,
          message:
            "Could not load Umami audience data from this PC. The Umami Cloud web dashboard still works when serve is off.",
        });
        return null;
      });
  }

  function renderMetrics(metrics) {
    metrics = metrics || {};
    var note = metrics.note || "Metrics reset when serve restarts.";
    setText("[data-metrics-note]", note);
    setText("[data-metrics-note-traffic]", note);
    setText("[data-metrics-note-errors]", note);

    setText(
      "[data-kpi-errors]",
      metrics.error_rate != null ? metrics.error_rate + "%" : "0%"
    );
    setText("[data-traffic-requests]", String(metrics.origin_requests_24h || 0));
    setText("[data-errors-5xx]", String((metrics.errors && metrics.errors.events_5xx) || 0));
    setText(
      "[data-errors-unexpected]",
      String((metrics.errors && metrics.errors.events_unexpected_4xx) || 0)
    );
    setText("[data-errors-routine]", String(metrics.routine_4xx_24h || 0));
    setText(
      "[data-errors-p95]",
      metrics.p95_ms != null ? metrics.p95_ms + " ms" : "—"
    );

    var buckets = metrics.buckets || [];
    renderBarChart("[data-chart-overview-requests]", buckets, "requests", { maxBars: 60 });
    renderBarChart("[data-chart-traffic-requests]", buckets, "requests", { maxBars: 180 });
    renderBarChart("[data-chart-errors-outages]", buckets, "outage_errors", { maxBars: 180 });
    renderRouteTable(metrics.routes || []);
    renderErrorEvents((metrics.errors && metrics.errors.recent) || []);
  }

  function renderActivity(rows) {
    var el = root() && root().querySelector("[data-activity-feed]");
    if (!el) return;
    el.innerHTML = "";
    if (!rows || !rows.length) {
      el.innerHTML = '<p class="snapshot-meta">No audit lines yet.</p>';
      return;
    }
    rows.slice().reverse().forEach(function (row) {
      var item = document.createElement("div");
      item.className = "ops-feed-item";
      var title = row.action || "event";
      if (row.game_id) title += " · " + shortId(row.game_id);
      if (row.model_id) title += " · " + row.model_id;
      item.innerHTML = "<time></time><div><strong></strong><div class='ops-feed-msg'></div></div>";
      item.querySelector("time").textContent = (row.ts || "").slice(11, 19) || "—";
      item.querySelector("strong").textContent = title;
      item.querySelector(".ops-feed-msg").textContent =
        row.game_type || row.user_agent || row.ip_hash || "";
      el.appendChild(item);
    });
  }

  function applySnapshot(data) {
    var disk = data.disk || {};
    var harness = data.harness_dir || {};
    var inbox = data.inbox || {};
    var live = data.live || {};
    var tunnel = data.tunnel || {};
    var health = data.health || {};
    var metrics = data.metrics || {};

    setText("[data-ops-updated]", "Updated " + fmtTime(data.generated_at));
    setText("[data-kpi-requests]", String(metrics.origin_requests_24h != null ? metrics.origin_requests_24h : 0));
    setText("[data-kpi-inbox]", String(inbox.unread != null ? inbox.unread : 0));
    setText("[data-kpi-disk]", fmtPct(disk.free_bytes, disk.total_bytes));
    setText(
      "[data-kpi-disk-detail]",
      fmtBytes(disk.used_bytes) + " used · " + fmtBytes(disk.total_bytes) + " total"
    );

    var badge = root() && root().querySelector("[data-inbox-badge]");
    if (badge) {
      var unread = inbox.unread || 0;
      badge.textContent = String(unread);
      badge.hidden = unread <= 0;
    }

    renderInboxList("[data-inbox-preview]", (inbox.latest || []).slice(0, 3), false);
    renderLiveGames(live.games || [], live.games_total || 0);
    renderLiveAttempts(live.puzzle_attempts || [], live.identify_attempts || []);
    renderActivity(data.activity || []);
    renderMetrics(metrics);

    setText("[data-machine-serve]", health.ok ? "up" : "down");
    setText("[data-machine-tunnel]", tunnel.pid ? "pid " + tunnel.pid : "none");
    setText("[data-machine-tunnel-url]", tunnel.url || "No quick-tunnel.url yet");
    setText("[data-machine-harness-size]", fmtBytes(harness.size_bytes));
    setText("[data-machine-harness-path]", harness.path || "");
    if (health.calibration_worker_ok === false) {
      setText("[data-machine-calibration]", "down");
    } else if (health.calibration_worker_ok === true) {
      setText("[data-machine-calibration]", "ok");
    } else {
      setText("[data-machine-calibration]", "in-process");
    }

    setText("[data-disk-drive]", disk.drive || "System");
    setText(
      "[data-disk-used]",
      fmtBytes(disk.used_bytes) + " / " + fmtBytes(disk.total_bytes)
    );
    var bar = root() && root().querySelector("[data-disk-bar]");
    if (bar && disk.total_bytes) {
      var usedPct = Math.min(100, Math.round((disk.used_bytes / disk.total_bytes) * 100));
      bar.style.width = usedPct + "%";
    }
    setText("[data-harness-size]", fmtBytes(harness.size_bytes));
    setText("[data-health-local]", health.ok ? "ok" : "fail");
    setText("[data-health-tunnel-file]", tunnel.url ? "set" : "empty");
    setText("[data-tunnel-status]", tunnel.pid ? "tracked" : "none");

    var serveChip = root() && root().querySelector("[data-ops-serve-chip]");
    if (serveChip) {
      serveChip.setAttribute("data-state", health.ok ? "online" : "offline");
    }
  }

  function refresh() {
    var snapshotReq = fetch("/api/ops/snapshot", {
      headers: LOOPBACK_HEADERS,
      cache: "no-store",
    }).then(function (res) {
      if (!res.ok) throw new Error("Snapshot HTTP " + res.status);
      return res.json();
    });
    var inboxReq = fetch("/api/contact/inbox", {
      headers: LOOPBACK_HEADERS,
      cache: "no-store",
    })
      .then(function (res) {
        if (!res.ok) return null;
        return res.json();
      })
      .catch(function () {
        return null;
      });
    return Promise.all([snapshotReq, inboxReq, fetchAudience()])
      .then(function (results) {
        showError("");
        applySnapshot(results[0]);
        if (results[1] && results[1].messages) {
          renderInboxList("[data-inbox-full]", results[1].messages, true);
        }
      })
      .catch(function (err) {
        showError(err && err.message ? err.message : "Could not load snapshot");
      });
  }

  function activateTab(id) {
    var panel = root();
    if (!panel) return;
    panel.querySelectorAll("[data-ops-tab]").forEach(function (btn) {
      var active = btn.getAttribute("data-ops-tab") === id;
      btn.setAttribute("aria-current", active ? "page" : null);
    });
    panel.querySelectorAll("[data-ops-section]").forEach(function (section) {
      var show = section.getAttribute("data-ops-section") === id;
      section.hidden = !show;
      section.classList.toggle("hidden", !show);
    });
    var copy = TAB_COPY[id] || TAB_COPY.overview;
    setText("[data-ops-title]", copy[0]);
    setText("[data-ops-subtitle]", copy[1]);
  }

  function initTabs() {
    var panel = root();
    if (!panel) return;
    panel.querySelectorAll("[data-ops-tab]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        activateTab(btn.getAttribute("data-ops-tab"));
      });
    });
    activateTab("overview");
  }

  document.addEventListener("DOMContentLoaded", function () {
    initTabs();
    initGoOnlineControls();
    refresh();
    setInterval(refresh, POLL_MS);
  });
})();
