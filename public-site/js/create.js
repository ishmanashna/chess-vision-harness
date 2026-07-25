(function () {
  "use strict";

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

  function createGame(apiKey, agentColor) {
    var body = {};
    if (agentColor && agentColor !== "random") {
      body.agent_color = agentColor;
    }
    return apiJson("/api/v1/games", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + apiKey,
      },
      body: JSON.stringify(body),
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

  function showResult(root, gameId, brief) {
    var result = root.querySelector("[data-create-result]");
    var form = root.querySelector("[data-create-form]");
    if (form) form.hidden = true;
    if (!result) return;
    result.hidden = false;
    result.innerHTML =
      '<div class="form-message form-message-ok">' +
      "Game created. " +
      '<a href="/g/' +
      escapeHtml(gameId) +
      '">Spectate this game</a>' +
      ' · <a href="/active/">Active games</a>' +
      "</div>" +
      '<p class="game-id-line">Game ID: <code>' +
      escapeHtml(gameId) +
      "</code></p>" +
      '<div class="brief-wrap">' +
      "<label for=\"agent-brief\"><strong>Agent prompt</strong> — paste into your agent</label>" +
      '<textarea id="agent-brief" readonly rows="18">' +
      escapeHtml(brief) +
      "</textarea>" +
      '<button type="button" class="btn btn-secondary" data-copy-brief>Copy prompt</button>' +
      "</div>";

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

  function mountCreatePage() {
    var root = document.querySelector("[data-create-page]");
    if (!root) return;

    var form = root.querySelector("[data-create-form]");
    var modelSelect = root.querySelector("#model-select");
    var newModelId = root.querySelector("#new-model-id");
    var newModelName = root.querySelector("#new-model-name");
    var agentColor = root.querySelector("#agent-color");
    var submitBtn = root.querySelector("[data-create-submit]");
    var messageEl = root.querySelector("[data-create-message]");
    var inscribeBtn = root.querySelector("[data-inscribe-submit]");

    function enableForm(online) {
      root.classList.toggle("create-online", online);
      if (form) form.hidden = !online;
      [modelSelect, newModelId, newModelName, agentColor, submitBtn, inscribeBtn].forEach(
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
            setMessage(messageEl, "ok", "Model inscribed. Select it below or create a game.");
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

        var modelId = (modelSelect && modelSelect.value || "").trim();
        var freshId = (newModelId && newModelId.value || "").trim();
        var freshName = (newModelName && newModelName.value || "").trim();
        var chosenId = freshId || modelId;

        if (!chosenId) {
          setMessage(messageEl, "error", "Select an inscribed model, or open Inscribe a new model below.");
          return;
        }

        submitBtn.disabled = true;
        setMessage(messageEl, "ok", "Creating game…");

        registerAgent(chosenId, freshId ? freshName || undefined : undefined)
          .then(function (reg) {
            if (!reg.api_key) throw new Error("No API key returned.");
            var color = agentColor ? agentColor.value : "random";
            return createGame(reg.api_key, color).then(function (game) {
              return { game: game, apiKey: reg.api_key };
            });
          })
          .then(function (ctx) {
            var game = ctx.game;
            var gameId = game.game_id;
            var brief = game.agent_brief;
            if (!gameId) throw new Error("No game id returned.");
            if (!brief) {
              throw new Error(
                "Server did not return agent_brief. Set CHESS_HARNESS_PUBLIC_URL on the game PC."
              );
            }
            showResult(root, gameId, brief);
          })
          .catch(function (err) {
            setMessage(messageEl, "error", err.message || "Create game failed.");
          })
          .finally(function () {
            submitBtn.disabled = false;
          });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", mountCreatePage);
})();
