(function () {
  "use strict";

  var pollTimer = null;
  var mode = "engine";
  var pairing = "find";
  var activeLobbyId = null;
  var activeLobbyApiKey = null;
  var matchApi = window.CVH && window.CVH.createMatch;
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

  function createDirectAvaa(whiteKey, blackKey, whiteId, blackId) {
    return apiJson("/api/v1/games/agent-vs-agent", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + whiteKey,
      },
      body: JSON.stringify({
        white_model_id: whiteId,
        black_model_id: blackId,
        peer_api_key: blackKey,
      }),
    });
  }

  function fillModelSelect(selectEl, agents, placeholder) {
    var html = '<option value="">' + escapeHtml(placeholder) + "</option>";
    agents.forEach(function (agent) {
      var id = agent.id || "";
      var label = agent.name && agent.name !== id ? agent.name + " (" + id + ")" : id;
      html +=
        '<option value="' + escapeHtml(id) + '">' + escapeHtml(label) + "</option>";
    });
    selectEl.innerHTML = html;
  }

  function loadAgents(selectEls) {
    var selects = Array.isArray(selectEls) ? selectEls : [selectEls];
    return apiJson("/api/v1/agents").then(function (data) {
      var agents = Array.isArray(data.agents) ? data.agents : [];
      selects.forEach(function (selectEl) {
        if (!selectEl) return;
        var placeholder =
          selectEl.id === "white-model-select"
            ? "Select white model…"
            : selectEl.id === "black-model-select"
              ? "Select black model…"
              : "Select inscribed model…";
        fillModelSelect(selectEl, agents, placeholder);
      });
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
    if (resultApi && resultApi.stopJoinPoll) resultApi.stopJoinPoll();
  }

  function setAvaaWaiting(root, submitBtn, waiting) {
    if (waiting) root.dataset.avaaWaiting = "1";
    else delete root.dataset.avaaWaiting;
    if (submitBtn) submitBtn.disabled = waiting;
  }

  function beginWaiting(root, submitBtn, lobbyId, apiKey) {
    activeLobbyId = lobbyId;
    activeLobbyApiKey = apiKey;
    setAvaaWaiting(root, submitBtn, true);
  }

  function clearWaiting(root, submitBtn) {
    activeLobbyId = null;
    activeLobbyApiKey = null;
    setAvaaWaiting(root, submitBtn, false);
  }

  function cancelActiveLobby() {
    if (!activeLobbyId || !activeLobbyApiKey || !matchApi || !matchApi.cancelLobby) {
      return Promise.resolve();
    }
    return matchApi.cancelLobby(apiJson, activeLobbyId, activeLobbyApiKey);
  }

  function showResult(root, gameId, brief, matched, messageEl, options) {
    if (!resultApi) return;
    setMessage(messageEl || root.querySelector("[data-create-message]"), null, "");
    resultApi.showBriefResult(root, gameId, brief, matched, Object.assign({ escapeHtml: escapeHtml }, options || {}));
  }

  function matchHelpers(root, messageEl, submitBtn) {
    return {
      stopPoll: stopPoll,
      setMessage: setMessage,
      showResult: function (r, gameId, brief, matched, msgEl, opts) {
        clearWaiting(root, submitBtn);
        showResult(r, gameId, brief, matched, msgEl, opts);
      },
      beginWaiting: function (lobbyId, apiKey) {
        beginWaiting(root, submitBtn, lobbyId, apiKey || activeLobbyApiKey);
      },
      clearWaiting: function () {
        clearWaiting(root, submitBtn);
      },
      setSubmitDisabled: function (disabled) {
        setAvaaWaiting(root, submitBtn, disabled);
      },
      schedule: function (fn, ms) {
        pollTimer = setTimeout(fn, ms);
      },
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
      return { apiKey: reg.api_key, modelId: chosenId };
    });
  }

  function resolveDirectPair(whiteSelect, blackSelect) {
    var whiteId = (whiteSelect && whiteSelect.value || "").trim();
    var blackId = (blackSelect && blackSelect.value || "").trim();
    if (!whiteId || !blackId) {
      return Promise.reject(new Error("Select both white and black models."));
    }
    // Same model twice is allowed (mirror match): mint two keys so each side binds.
    return Promise.all([registerAgent(whiteId), registerAgent(blackId)]).then(function (regs) {
      if (!regs[0].api_key || !regs[1].api_key) throw new Error("No API key returned.");
      return {
        whiteId: whiteId,
        blackId: blackId,
        whiteKey: regs[0].api_key,
        blackKey: regs[1].api_key,
      };
    });
  }

  function parseModeFromUrl() {
    var search = window.location.search || "";
    if (search.indexOf("mode=avaa") >= 0) return "avaa";
    return "engine";
  }

  function applyPairingVisibility(root) {
    var pairingTabs = root.querySelector("[data-avaa-pairing-tabs]");
    var singleRow = root.querySelector("[data-single-model-row]");
    var directFields = root.querySelector("[data-avaa-direct-fields]");
    var isAvaa = mode === "avaa";
    var isDirect = isAvaa && pairing === "direct";
    if (pairingTabs) pairingTabs.hidden = !isAvaa;
    if (singleRow) singleRow.hidden = isDirect;
    if (directFields) directFields.hidden = !isDirect;
    if (pairingTabs) {
      pairingTabs.querySelectorAll("[data-pairing]").forEach(function (tab) {
        var active = tab.getAttribute("data-pairing") === pairing;
        tab.classList.toggle("is-active", active);
        tab.setAttribute("aria-selected", active ? "true" : "false");
      });
    }
  }

  function setPairing(root, next) {
    pairing = next === "direct" ? "direct" : "find";
    applyPairingVisibility(root);
    updateSubmitLabel(root);
  }

  function updateSubmitLabel(root) {
    var submit = root.querySelector("[data-create-submit]");
    if (!submit) return;
    if (mode === "avaa") {
      submit.textContent = pairing === "direct" ? "Create direct game" : "Find match";
    } else {
      submit.textContent = "Create rated game";
    }
  }

  function setMode(root, next) {
    mode = next === "avaa" ? "avaa" : "engine";
    if (mode !== "avaa") pairing = "find";
    root.querySelectorAll(".mode-tabs:not(.pairing-tabs) .mode-tab").forEach(function (tab) {
      var active = tab.getAttribute("data-mode") === mode;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    var heading = root.querySelector("[data-mode-heading]");
    var asideEngine = root.querySelector("[data-aside-engine]");
    var asideAvaa = root.querySelector("[data-aside-avaa]");
    if (heading) {
      if (mode === "avaa" && pairing === "direct") {
        heading.textContent = "Rated Direct (pick both sides)";
      } else if (mode === "avaa") {
        heading.textContent = "Rated game vs agent";
      } else {
        heading.textContent = "Rated game vs engine";
      }
    }
    if (asideEngine) asideEngine.hidden = mode !== "engine";
    if (asideAvaa) asideAvaa.hidden = mode !== "avaa";
    applyPairingVisibility(root);
    updateSubmitLabel(root);
    try {
      var url = new URL(window.location.href);
      if (mode === "avaa") url.searchParams.set("mode", "avaa");
      else url.searchParams.delete("mode");
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    } catch (e) {
      /* ignore */
    }
  }

  function submitMessage() {
    if (mode === "avaa" && pairing === "direct") return "Creating Direct game…";
    if (mode === "avaa") return "Finding match…";
    return "Creating game…";
  }

  function mountCreatePage() {
    var root = document.querySelector("[data-create-page]");
    if (!root) return;

    var form = root.querySelector("[data-create-form]");
    var modelSelect = root.querySelector("#model-select");
    var whiteSelect = root.querySelector("#white-model-select");
    var blackSelect = root.querySelector("#black-model-select");
    var newModelId = root.querySelector("#new-model-id");
    var newModelName = root.querySelector("#new-model-name");
    var submitBtn = root.querySelector("[data-create-submit]");
    var messageEl = root.querySelector("[data-create-message]");
    var inscribeBtn = root.querySelector("[data-inscribe-submit]");

    setMode(root, parseModeFromUrl());

    function enableForm(online) {
      root.classList.toggle("create-online", online);
      if (form) form.hidden = !online;
      var waiting = !!root.dataset.avaaWaiting;
      [modelSelect, whiteSelect, blackSelect, newModelId, newModelName, inscribeBtn].forEach(
        function (el) {
          if (el) el.disabled = !online;
        }
      );
      root.querySelectorAll("[data-avaa-pairing-tabs] .mode-tab").forEach(function (tab) {
        tab.disabled = !online;
      });
      if (submitBtn) submitBtn.disabled = !online || waiting;
    }

    window.CVH.applyHealthUi({
      onHealth: function (health) {
        enableForm(health.online);
        if (!health.online) return;
        loadAgents([modelSelect, whiteSelect, blackSelect]).catch(function (err) {
          setMessage(messageEl, "error", err.message || "Could not load models.");
        });
      },
    });

    root.querySelectorAll(".mode-tabs:not(.pairing-tabs) .mode-tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        stopPoll();
        cancelActiveLobby().finally(function () {
          clearWaiting(root, submitBtn);
          setMessage(messageEl, null, "");
          setMode(root, tab.getAttribute("data-mode"));
        });
      });
    });

    root.querySelectorAll("[data-avaa-pairing-tabs] .mode-tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        if (root.dataset.avaaWaiting) return;
        stopPoll();
        cancelActiveLobby().finally(function () {
          clearWaiting(root, submitBtn);
          setMessage(messageEl, null, "");
          setPairing(root, tab.getAttribute("data-pairing"));
          var heading = root.querySelector("[data-mode-heading]");
          if (heading && mode === "avaa") {
            heading.textContent =
              pairing === "direct" ? "Rated Direct (pick both sides)" : "Rated game vs agent";
          }
        });
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
            return loadAgents([modelSelect, whiteSelect, blackSelect]);
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
        if (root.dataset.avaaWaiting) return;
        setMessage(messageEl, null, "");
        stopPoll();
        submitBtn.disabled = true;
        setMessage(messageEl, "ok", submitMessage());

        var cancelPromise =
          mode === "avaa"
            ? cancelActiveLobby().then(function () {
                clearWaiting(root, submitBtn);
              })
            : Promise.resolve();

        cancelPromise
          .then(function () {
            if (mode === "avaa" && pairing === "direct") {
              return resolveDirectPair(whiteSelect, blackSelect).then(function (pair) {
                return createDirectAvaa(
                  pair.whiteKey,
                  pair.blackKey,
                  pair.whiteId,
                  pair.blackId
                ).then(function (game) {
                  return { kind: "direct", game: game };
                });
              });
            }
            return resolveModelAndKey(modelSelect, newModelId, newModelName).then(function (ctx) {
              if (mode === "avaa") {
                activeLobbyApiKey = ctx.apiKey;
                if (!matchApi) throw new Error("Matchmaking module missing.");
                return matchApi.findMatch(apiJson, ctx.apiKey).then(function (data) {
                  return { kind: "avaa", data: data, apiKey: ctx.apiKey };
                });
              }
              return createEngineGame(ctx.apiKey).then(function (game) {
                return { kind: "engine", game: game };
              });
            });
          })
          .then(function (ctx) {
            if (ctx.kind === "direct") {
              if (!resultApi || !resultApi.showDualBriefResult) {
                throw new Error("Result module missing.");
              }
              resultApi.showDualBriefResult(root, ctx.game, { escapeHtml: escapeHtml });
              return;
            }
            if (ctx.kind === "avaa") {
              activeLobbyApiKey = ctx.apiKey;
              matchApi.handleAvaaResponse(
                apiJson,
                root,
                ctx.data,
                ctx.apiKey,
                messageEl,
                matchHelpers(root, messageEl, submitBtn)
              );
              return;
            }
            if (!resultApi) throw new Error("Result module missing.");
            var game = resultApi.requireBrief(ctx.game, false);
            showResult(root, game.game_id, game.agent_brief, false, messageEl);
          })
          .catch(function (err) {
            clearWaiting(root, submitBtn);
            setMessage(messageEl, "error", err.message || "Request failed.");
          })
          .finally(function () {
            if (!root.dataset.avaaWaiting && submitBtn) submitBtn.disabled = false;
          });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", mountCreatePage);
})();
