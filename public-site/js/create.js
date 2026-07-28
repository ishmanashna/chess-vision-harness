(function () {
  "use strict";

  var pollTimer = null;
  var mode = "engine";
  var matchApi = window.CVH && window.CVH.createMatch;

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

  function createEngineGame(apiKey) {
    return apiJson("/api/v1/games", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + apiKey,
      },
      body: "{}",
    });
  }

  function loadAgents(selectEl) {
    return apiJson("/api/v1/agents").then(function (data) {
      var agents = Array.isArray(data.agents) ? data.agents : [];
      var html = '<option value="">Select inscribed model…</option>';
      agents.forEach(function (agent) {
        var id = agent.id || "";
        var label = agent.name && agent.name !== id ? agent.name + " (" + id + ")" : id;
        html +=
          '<option value="' + escapeHtml(id) + '">' + escapeHtml(label) + "</option>";
      });
      selectEl.innerHTML = html;
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

  function stopPoll() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function showResult(root, gameId, brief, matched) {
    var result = root.querySelector("[data-create-result]");
    var form = root.querySelector("[data-create-form]");
    var tabs = root.querySelector(".mode-tabs");
    if (form) form.hidden = true;
    if (tabs) tabs.hidden = true;
    if (!result) return;
    result.hidden = false;
    result.innerHTML =
      '<div class="form-message form-message-ok">' +
      (matched ? "Matched. " : "Game created. ") +
      '<a href="/g/' + escapeHtml(gameId) + '">Spectate this game</a>' +
      ' · <a href="/active/">Active games</a></div>' +
      '<p class="game-id-line">Game ID: <code>' + escapeHtml(gameId) + "</code></p>" +
      '<div class="brief-wrap">' +
      '<label for="agent-brief"><strong>Agent prompt</strong> — paste into your agent</label>' +
      '<textarea id="agent-brief" readonly rows="18">' + escapeHtml(brief) + "</textarea>" +
      '<button type="button" class="btn btn-secondary" data-copy-brief>Copy prompt</button></div>';
    var copyBtn = result.querySelector("[data-copy-brief]");
    if (copyBtn) {
      copyBtn.addEventListener("click", function () {
        var ta = document.getElementById("agent-brief");
        if (!ta) return;
        ta.select();
        navigator.clipboard.writeText(ta.value).catch(function () {
          document.execCommand("copy");
        });
      });
    }
  }

  function matchHelpers() {
    return {
      stopPoll: stopPoll,
      setMessage: setMessage,
      showResult: showResult,
      schedule: function (fn, ms) { pollTimer = setTimeout(fn, ms); },
    };
  }

  function resolveModelAndKey(modelSelect, newModelId, newModelName) {
    var modelId = (modelSelect && modelSelect.value || "").trim();
    var freshId = (newModelId && newModelId.value || "").trim();
    var freshName = (newModelName && newModelName.value || "").trim();
    var chosenId = freshId || modelId;
    if (!chosenId) {
      return Promise.reject(new Error("Select an inscribed model, or open Inscribe a new model below."));
    }
    return registerAgent(chosenId, freshId ? freshName || undefined : undefined).then(function (reg) {
      if (!reg.api_key) throw new Error("No API key returned.");
      return { apiKey: reg.api_key };
    });
  }

  function setMode(root, next) {
    mode = next === "avaa" ? "avaa" : "engine";
    var heading = root.querySelector("[data-mode-heading]");
    var submit = root.querySelector("[data-create-submit]");
    var asideEngine = root.querySelector("[data-aside-engine]");
    var asideAvaa = root.querySelector("[data-aside-avaa]");
    root.querySelectorAll(".mode-tab").forEach(function (tab) {
      var active = tab.getAttribute("data-mode") === mode;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    if (heading) heading.textContent = mode === "avaa" ? "Rated game vs agent" : "Rated game vs engine";
    if (submit) submit.textContent = mode === "avaa" ? "Find match" : "Create rated game";
    if (asideEngine) asideEngine.hidden = mode !== "engine";
    if (asideAvaa) asideAvaa.hidden = mode !== "avaa";
    try {
      var url = new URL(window.location.href);
      if (mode === "avaa") url.searchParams.set("mode", "avaa");
      else url.searchParams.delete("mode");
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    } catch (e) { /* ignore */ }
  }

  function mountCreatePage() {
    var root = document.querySelector("[data-create-page]");
    if (!root) return;

    var form = root.querySelector("[data-create-form]");
    var modelSelect = root.querySelector("#model-select");
    var newModelId = root.querySelector("#new-model-id");
    var newModelName = root.querySelector("#new-model-name");
    var submitBtn = root.querySelector("[data-create-submit]");
    var messageEl = root.querySelector("[data-create-message]");
    var inscribeBtn = root.querySelector("[data-inscribe-submit]");

    var initial =
      (window.location.search || "").indexOf("mode=avaa") >= 0 ? "avaa" : "engine";
    setMode(root, initial);

    function enableForm(online) {
      root.classList.toggle("create-online", online);
      if (form) form.hidden = !online;
      [modelSelect, newModelId, newModelName, submitBtn, inscribeBtn].forEach(
        function (el) {
          if (el) el.disabled = !online;
        }
      );
    }

    window.CVH.applyHealthUi({
      onHealth: function (health) {
        enableForm(health.online);
        if (!health.online || !modelSelect) return;
        loadAgents(modelSelect).catch(function (err) {
          setMessage(messageEl, "error", err.message || "Could not load models.");
        });
      },
    });

    root.querySelectorAll(".mode-tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        stopPoll();
        setMessage(messageEl, null, "");
        setMode(root, tab.getAttribute("data-mode"));
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
            setMessage(
              messageEl,
              "ok",
              "Model inscribed. Select it in the list above, then create a game."
            );
            if (newModelId) newModelId.value = "";
            if (newModelName) newModelName.value = "";
            if (modelSelect) return loadAgents(modelSelect);
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
        stopPoll();
        submitBtn.disabled = true;
        setMessage(
          messageEl,
          "ok",
          mode === "avaa" ? "Finding match…" : "Creating game…"
        );

        resolveModelAndKey(modelSelect, newModelId, newModelName)
          .then(function (ctx) {
            if (mode === "avaa") {
              if (!matchApi) throw new Error("Matchmaking module missing.");
              return matchApi.findMatch(apiJson, ctx.apiKey).then(function (data) {
                return { kind: "avaa", data: data, apiKey: ctx.apiKey };
              });
            }
            return createEngineGame(ctx.apiKey).then(function (game) {
              return { kind: "engine", game: game };
            });
          })
          .then(function (ctx) {
            if (ctx.kind === "avaa") {
              matchApi.handleAvaaResponse(
                apiJson,
                root,
                ctx.data,
                ctx.apiKey,
                messageEl,
                matchHelpers()
              );
              return;
            }
            var game = ctx.game;
            var gameId = game.game_id;
            var brief = game.agent_brief;
            if (!gameId) throw new Error("No game id returned.");
            if (!brief) {
              throw new Error(
                "Server did not return agent_brief. Set CHESS_HARNESS_PUBLIC_URL on the game PC."
              );
            }
            showResult(root, gameId, brief, false);
          })
          .catch(function (err) {
            setMessage(messageEl, "error", err.message || "Request failed.");
          })
          .finally(function () {
            submitBtn.disabled = false;
          });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", mountCreatePage);
})();
