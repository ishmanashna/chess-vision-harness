/* Read-only experiment filters, summaries, and safe run-artifact links. */
(function () {
  "use strict";
  var offset = 0, generation = 0, busy = false, queued = false, lastRuns = 0;
  var filters = {};
  function el(selector) { return document.querySelector(selector); }
  function text(selector, value) { var node = el(selector); if (node) node.textContent = value; }
  function visible() { var node = el('[data-ops-section="prompt-test"]'); return node && !node.hidden && !document.hidden; }
  function number(value, digits) { return value == null ? "—" : Number(value).toFixed(digits || 0); }
  function query() {
    var params = new URLSearchParams();
    Object.keys(filters).forEach(function (key) { if (filters[key]) params.set(key, filters[key]); });
    params.set("offset", offset);
    params.set("limit", "100");
    return "/api/ops/prompt-test?" + params.toString();
  }
  function link(cell, url, label) {
    var node = document.createElement("a"); node.href = url; node.textContent = label;
    cell.appendChild(node);
  }
  function table(selector, rows, cells, empty) {
    var body = el(selector); if (!body) return;
    body.replaceChildren();
    if (!rows.length) {
      var tr = document.createElement("tr"), td = document.createElement("td");
      td.colSpan = cells; td.textContent = empty; tr.appendChild(td); body.appendChild(tr);
    }
    rows.forEach(function (values) {
      var tr = document.createElement("tr");
      values.forEach(function (value) {
        var td = document.createElement("td");
        if (typeof value === "function") value(td); else td.textContent = String(value == null ? "—" : value);
        tr.appendChild(td);
      }); body.appendChild(tr);
    });
  }
  function metric(value, reason, digits) {
    return function (td) { td.textContent = number(value, digits); if (reason) td.title = reason; };
  }
  function fillOptions(options) {
    var keys = { run_id: "run_id", model: "model_id", pack: "prompt_pack", opponent: "opponent_id", status: "status" };
    Object.keys(keys).forEach(function (key) {
      var select = el('[data-experiment-filter="' + key + '"]');
      if (!select) return;
      select.replaceChildren();
      [""].concat(options[keys[key]] || []).forEach(function (value) {
        var opt = document.createElement("option"); opt.value = value;
        opt.textContent = value === "legacy-unassigned" ? "Legacy / unassigned" : value || "All";
        select.appendChild(opt);
      }); select.value = filters[key] || "";
    });
  }
  function render(data) {
    fillOptions(data.options || {});
    var summary = data.summary || {};
    text("[data-prompt-test-meta]", (data.total || 0) + " matching games · " + (summary.analysed || 0) +
      " analysed finishes · live " + (summary.in_progress || 0) + " · abandoned " + (summary.abandoned || 0) +
      " · failed " + (summary.failed || 0) + " · excluded " + (summary.excluded || 0) + " · no result " + (summary.no_result || 0));
    text("[data-experiment-scope]", data.scope_note || "");
    text("[data-experiment-status]", "Updated " + new Date(data.generated_at).toLocaleString());
    text("[data-experiment-page]", data.total ? "Games " + (offset + 1) + "–" + (offset + data.games.length) + " of " + data.total : "No matching games");
    el("[data-experiment-prev]").disabled = offset === 0;
    el("[data-experiment-next]").disabled = !data.has_more;
    table("[data-prompt-test-body]", (data.packs || []).map(function (p) {
      var reason = p.analysed ? p.analysed + " analysed scored finishes" : "No analysed scored finishes in this selection.";
      return [p.title, p.total, p.in_progress, p.finished, p.abandoned, p.failed, p.excluded,
        p.wins + "–" + p.draws + "–" + p.losses, metric(p.mean_accuracy, reason, 1), metric(p.mean_play_rating, reason)];
    }), 10, "No packs match these filters.");
    table("[data-prompt-test-games]", (data.games || []).map(function (g) {
      return [g.title, g.run_id === "legacy-unassigned" ? "Legacy / unassigned" : g.run_id, g.model_id,
        function (td) { link(td, "/g/" + encodeURIComponent(g.game_id), g.game_id); }, g.agent_color,
        g.opponent_id, g.status, g.outcome ? g.outcome + " · " + g.result : "—",
        metric(g.accuracy, g.metric_reason, 1), metric(g.play_rating, g.metric_reason)];
    }), 10, "No games match these filters.");
    var chats = el("[data-prompt-test-chats]"); chats.replaceChildren();
    (data.chats || []).forEach(function (chat) {
      var details = document.createElement("details"), heading = document.createElement("summary");
      heading.textContent = chat.title + " · " + chat.game_id; details.appendChild(heading);
      (chat.messages || []).forEach(function (msg) {
        var p = document.createElement("p"); p.textContent = (msg.speaker || "seat " + (msg.seat || "?")) + ": " + (msg.text || msg.uci || "");
        details.appendChild(p);
      }); chats.appendChild(details);
    });
    if (!data.chats.length) chats.textContent = "No committee chat on this game page.";
  }
  function refreshRuns() {
    if (Date.now() - lastRuns < 60000) return;
    lastRuns = Date.now();
    text("[data-experiment-runs-status]", "Loading run records…");
    window.CVH.opsRequest("runs", "/api/ops/experiments").then(function (data) {
      table("[data-experiment-runs]", data.runs.map(function (run) {
        return [run.experiment_id + " / " + run.run_id, run.synthetic ? "Synthetic" : run.model,
          run.status, run.last_progress_at || "—", function (td) {
            link(td, run.report_url, "Safe report"); td.appendChild(document.createTextNode(" · "));
            link(td, run.events_url, "Safe events");
          }];
      }), 5, "No version-1 run manifests yet.");
      text("[data-experiment-runs-status]", data.note);
    }).catch(function (err) { lastRuns = 0; text("[data-experiment-runs-status]", "Run records: " + err.message); });
  }
  function refresh() {
    if (!visible()) return;
    refreshRuns();
    if (busy) return;
    busy = true;
    var current = generation;
    text("[data-experiment-status]", "Loading experiment evidence…");
    window.CVH.opsRequest("experiments", query()).then(function (data) {
      if (!data.summary || !data.options) throw new Error("Serving process has older Ops code. Restart localhost after active games finish to load Batch 3.");
      if (current === generation) render(data);
    }).catch(function (err) {
      if (current === generation) text("[data-experiment-status]", "A/B: " + err.message);
    }).finally(function () {
      busy = false;
      if (queued) { queued = false; refresh(); }
    });
  }
  function change() {
    generation++; offset = 0; queued = busy;
    table("[data-prompt-test-body]", [], 10, "Loading selected evidence…");
    table("[data-prompt-test-games]", [], 10, "Loading selected evidence…");
    text("[data-prompt-test-meta]", "");
    text("[data-prompt-test-chats]", "");
    text("[data-experiment-scope]", "Selection is loading; results from prior filters are cleared.");
    refresh();
  }
  window.CVH = window.CVH || {};
  window.CVH.refreshOpsExperiments = refresh;
  document.addEventListener("DOMContentLoaded", function () {
    var params = new URLSearchParams(window.location.search);
    document.querySelectorAll("[data-experiment-filter]").forEach(function (select) {
      var key = select.getAttribute("data-experiment-filter");
      filters[key] = params.get(key) || select.value;
      if (key === "family") select.value = filters[key];
      select.addEventListener("change", function () {
        filters[key] = select.value;
        if (key === "family") Object.keys(filters).forEach(function (k) { if (k !== "family") filters[k] = ""; });
        change();
      });
    });
    el("[data-experiment-prev]").addEventListener("click", function () { offset = Math.max(0, offset - 100); generation++; queued = busy; refresh(); });
    el("[data-experiment-next]").addEventListener("click", function () { offset += 100; generation++; queued = busy; refresh(); });
  });
})();
