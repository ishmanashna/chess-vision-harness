(function () {
  "use strict";

  var REDIRECT_MS = 4000;
  var redirectTimer = null;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function apiJson(url, options) {
    return fetch(url, options).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var err = new Error((data && data.error) || "Request failed");
          err.status = res.status;
          err.payload = data;
          throw err;
        }
        return data;
      });
    });
  }

  function registerAgent(modelId, displayName) {
    var body = { id: modelId };
    if (displayName) body.name = displayName;
    return apiJson("/api/v1/agents", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  function startAttempt(kind, apiKey, ratingMin, ratingMax) {
    var params = [];
    if (ratingMin) params.push("rating_min=" + encodeURIComponent(ratingMin));
    if (ratingMax) params.push("rating_max=" + encodeURIComponent(ratingMax));
    var suffix = params.length ? "?" + params.join("&") : "";
    var path = kind === "identify" ? "/api/v1/identify/start" : "/api/v1/puzzles/start";
    return apiJson(path + suffix, {
      method: "POST",
      headers: { authorization: "Bearer " + apiKey },
    });
  }

  function fillModelSelect(selectEl, agents) {
    var html = '<option value="">Select inscribed model…</option>';
    agents.forEach(function (agent) {
      var id = agent.id || "";
      var label = agent.name && agent.name !== id ? agent.name + " (" + id + ")" : id;
      html +=
        '<option value="' + escapeHtml(id) + '">' + escapeHtml(label) + "</option>";
    });
    selectEl.innerHTML = html;
  }

  function loadAgents(selectEl) {
    return apiJson("/api/v1/agents").then(function (data) {
      var agents = Array.isArray(data.agents) ? data.agents : [];
      fillModelSelect(selectEl, agents);
      return agents;
    });
  }

  function setMessage(el, type, text) {
    if (!el) return;
    if (!text) {
      el.hidden = true;
      el.textContent = "";
      el.className = "form-message";
      return;
    }
    el.hidden = false;
    el.className = "form-message " + (type === "error" ? "form-message-error" : "form-message-ok");
    el.textContent = text;
  }

  function clearRedirect() {
    if (redirectTimer) {
      clearTimeout(redirectTimer);
      redirectTimer = null;
    }
  }

  function renderBriefCollapsible(brief, esc, watchUrl, kindLabel) {
    return (
      '<div class="brief-wrap">' +
      '<div class="brief-toolbar">' +
      '<a class="btn btn-primary" href="' +
      esc(watchUrl) +
      '">Open watch page</a>' +
      '<button type="button" class="btn btn-secondary" data-copy-brief>Copy prompt</button>' +
      "</div>" +
      '<details class="brief-collapsible">' +
      "<summary>Show agent prompt</summary>" +
      '<textarea readonly rows="18">' +
      esc(brief) +
      "</textarea>" +
      "</details>" +
      '<p class="card-hint">Paste this prompt into your vision agent. The watch page opens in a moment.</p>' +
      "</div>"
    );
  }

  function wireCopyBrief(result) {
    result.querySelectorAll("[data-copy-brief]").forEach(function (copyBtn) {
      copyBtn.addEventListener("click", function () {
        var wrap = copyBtn.closest(".brief-wrap");
        var ta = wrap ? wrap.querySelector("textarea") : null;
        if (!ta) return;
        ta.select();
        navigator.clipboard.writeText(ta.value).catch(function () {
          document.execCommand("copy");
        });
      });
    });
  }

  function showResult(root, kind, data, modelLabel) {
    var result = root.querySelector("[data-launcher-result]");
    if (!result) return;
    clearRedirect();
    var attemptId = data.attempt_id;
    var watchPath = kind === "identify" ? "/i/" + attemptId : "/p/" + attemptId;
    result.hidden = false;
    result.innerHTML =
      '<div class="form-message form-message-ok">' +
      "<strong>" +
      escapeHtml(kind === "identify" ? "Board identification started" : "Puzzle started") +
      "</strong> · " +
      escapeHtml(modelLabel) +
      ' · <a href="/leaderboard/?tab=' +
      (kind === "identify" ? "identify" : "puzzles") +
      '">Leaderboard</a></div>' +
      '<p class="game-id-line">Attempt ID: <code>' +
      escapeHtml(attemptId) +
      "</code></p>" +
      (data.agent_brief
        ? renderBriefCollapsible(data.agent_brief, escapeHtml, watchPath, kind)
        : '<p class="form-message form-message-error">No agent prompt was returned — check CHESS_HARNESS_PUBLIC_URL on the game PC.</p>') +
      '<p class="card-hint">Redirecting to the watch page…</p>';
    wireCopyBrief(result);
    redirectTimer = window.setTimeout(function () {
      window.location.assign(watchPath);
    }, REDIRECT_MS);
  }

  function setTab(root, name) {
    var next = name === "identify" ? "identify" : "puzzles";
    root.querySelectorAll("[data-launcher-tab]").forEach(function (tab) {
      var active = tab.getAttribute("data-launcher-tab") === next;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    root.querySelectorAll("[data-launcher-panel]").forEach(function (panel) {
      panel.hidden = panel.getAttribute("data-launcher-panel") !== next;
    });
    var heading = root.querySelector("[data-launcher-heading]");
    if (heading) heading.textContent = next === "identify" ? "Board identification" : "Puzzles";
    try {
      var url = new URL(window.location.href);
      url.searchParams.set("tab", next);
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    } catch (e) {
      /* ignore */
    }
  }

  function initialTab() {
    var search = window.location.search || "";
    if (search.indexOf("tab=identify") >= 0) return "identify";
    return "puzzles";
  }

  function mountLauncherPage() {
    var root = document.querySelector("[data-launcher-page]");
    if (!root) return;

    var form = root.querySelector("[data-launcher-form]");
    var modelSelect = root.querySelector("#launcher-model-select");
    var newModelId = root.querySelector("#launcher-new-model-id");
    var newModelName = root.querySelector("#launcher-new-model-name");
    var submitBtn = root.querySelector("[data-launcher-submit]");
    var messageEl = root.querySelector("[data-launcher-message]");
    var inscribeBtn = root.querySelector("[data-launcher-inscribe]");
    var resultEl = root.querySelector("[data-launcher-result]");

    setTab(root, initialTab());

    function enableForm(online) {
      root.classList.toggle("create-online", online);
      if (form) form.hidden = !online;
      [modelSelect, newModelId, newModelName, inscribeBtn].forEach(
        function (el) {
          if (el) el.disabled = !online;
        }
      );
      if (submitBtn) submitBtn.disabled = !online;
    }

    window.CVH.applyHealthUi({
      onHealth: function (health) {
        enableForm(health.online);
        if (!health.online) return;
        loadAgents(modelSelect).catch(function (err) {
          setMessage(messageEl, "error", err.message || "Could not load models.");
        });
      },
    });

    root.querySelectorAll("[data-launcher-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        setTab(root, tab.getAttribute("data-launcher-tab"));
      });
    });

    if (inscribeBtn) {
      inscribeBtn.addEventListener("click", function () {
        setMessage(messageEl, null, "");
        var id = (newModelId && newModelId.value || "").trim();
        var name = (newModelName && newModelName.value || "").trim();
        if (!id) {
          setMessage(messageEl, "error", "Enter a model id to inscribe.");
          return;
        }
        inscribeBtn.disabled = true;
        registerAgent(id, name || undefined)
          .then(function () {
            setMessage(messageEl, "ok", "Model inscribed. Select it above, then start.");
            if (newModelId) newModelId.value = "";
            if (newModelName) newModelName.value = "";
            return loadAgents(modelSelect);
          })
          .catch(function (err) {
            setMessage(messageEl, "error", err.message || "Inscribe failed.");
          })
          .finally(function () {
            inscribeBtn.disabled = false;
          });
      });
    }

    if (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        setMessage(messageEl, null, "");
        submitBtn.disabled = true;
        resultEl.hidden = true;
        resultEl.innerHTML = "";

        var modelId = (modelSelect && modelSelect.value || "").trim();
        if (!modelId) {
          setMessage(messageEl, "error", "Select an inscribed model first.");
          submitBtn.disabled = false;
          return;
        }
        var kind = "puzzles";
        var activeTab = root.querySelector("[data-launcher-tab].is-active");
        if (activeTab) kind = activeTab.getAttribute("data-launcher-tab");
        var label = (modelSelect.selectedOptions[0] && modelSelect.selectedOptions[0].textContent) || modelId;
        setMessage(messageEl, "ok", "Starting…");

        registerAgent(modelId)
          .then(function (reg) {
            if (!reg.api_key) throw new Error("No API key returned.");
            return startAttempt(kind, reg.api_key);
          })
          .then(function (data) {
            setMessage(messageEl, null, "");
            showResult(root, kind, data, label);
          })
          .catch(function (err) {
            setMessage(messageEl, "error", err.message || "Start failed.");
          })
          .finally(function () {
            submitBtn.disabled = false;
          });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", mountLauncherPage);
})();
