(function () {
  "use strict";

  var pollTimer = null;
  var mode = "engine";
  var matchApi = window.CVH && window.CVH.createMatch;
  var humanApi = window.CVH && window.CVH.createHuman;

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
    if (humanApi) humanApi.showBriefResult(root, gameId, brief, matched, escapeHtml, "");
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

  function normalizeMode(next) {
    if (next === "avaa") return "avaa";
    if (humanApi && humanApi.isHumanMode(next)) return "human";
    return "engine";
  }

  function setMode(root, next) {
    mode = normalizeMode(next);
    root.querySelectorAll(".mode-tab").forEach(function (tab) {
      var active = tab.getAttribute("data-mode") === mode;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    if (humanApi) {
      humanApi.toggleHumanChrome(root, mode);
      humanApi.updateUrlMode(mode);
    }
  }

  function submitMessage() {
    if (mode === "avaa") return "Finding match…";
    return "Creating game…";
  }

  function mountCreatePage() {
    var root = document.querySelector("[data-create-page]");
    if (!root) return;

    var form = root.querySelector("[data-create-form]");
    var modelSelect = root.querySelector("#model-select");
    var newModelId = root.querySelector("#new-model-id");
    var newModelName = root.querySelector("#new-model-name");
    var humanNickname = root.querySelector("#human-nickname");
    var submitBtn = root.querySelector("[data-create-submit]");
    var messageEl = root.querySelector("[data-create-message]");
    var inscribeBtn = root.querySelector("[data-inscribe-submit]");

    setMode(root, humanApi ? humanApi.parseModeFromUrl() : "engine");

    function enableForm(online) {
      root.classList.toggle("create-online", online);
      if (form) form.hidden = !online;
      [modelSelect, newModelId, newModelName, humanNickname, submitBtn, inscribeBtn].forEach(
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
        setMessage(messageEl, "ok", submitMessage());

        resolveModelAndKey(modelSelect, newModelId, newModelName)
          .then(function (ctx) {
            if (humanApi && humanApi.isHumanMode(mode)) {
              var nickname = (humanNickname && humanNickname.value || "").trim();
              return humanApi.createHumanGame(apiJson, ctx.apiKey, nickname).then(function (game) {
                return { kind: "human", game: game };
              });
            }
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
            if (ctx.kind === "human") {
              var humanGame = humanApi.requireBrief(ctx.game, true);
              humanApi.showHumanResult(
                root,
                humanGame.game_id,
                humanGame.agent_brief,
                humanGame.play_token,
                escapeHtml
              );
              return;
            }
            var game = humanApi ? humanApi.requireBrief(ctx.game, false) : ctx.game;
            showResult(root, game.game_id, game.agent_brief, false);
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
