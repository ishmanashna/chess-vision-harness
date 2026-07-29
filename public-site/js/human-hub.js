(function () {
  "use strict";

  var humanApi = window.CVH && window.CVH.createHuman;
  var resultApi = window.CVH && window.CVH.createResult;

  function escapeHtml(value) {
    if (resultApi && resultApi.escapeHtml) return resultApi.escapeHtml(value);
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

  function mountHumanHub() {
    var root = document.querySelector("[data-human-page]");
    if (!root || !humanApi || !resultApi) return;

    var form = root.querySelector("[data-human-form]");
    var modelSelect = root.querySelector("#model-select");
    var newModelId = root.querySelector("#new-model-id");
    var newModelName = root.querySelector("#new-model-name");
    var humanNickname = root.querySelector("#human-nickname");
    var submitBtn = root.querySelector("[data-human-submit]");
    var messageEl = root.querySelector("[data-human-message]");
    var inscribeBtn = root.querySelector("[data-inscribe-submit]");

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
        if (humanApi.stopWaitPoll) humanApi.stopWaitPoll();
        submitBtn.disabled = true;
        setMessage(messageEl, "ok", "Creating game…");

        resolveModelAndKey(modelSelect, newModelId, newModelName)
          .then(function (ctx) {
            var nickname = (humanNickname && humanNickname.value || "").trim();
            return humanApi.createHumanGame(apiJson, ctx.apiKey, nickname);
          })
          .then(function (game) {
            var ready = resultApi.requireBrief(game, true);
            humanApi.showHumanResult(root, ready, escapeHtml);
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

  document.addEventListener("DOMContentLoaded", mountHumanHub);
})();
