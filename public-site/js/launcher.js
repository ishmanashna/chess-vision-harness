(function () {
  "use strict";

  /* Unified launcher: one page, five flows (engine / avaa / playground / puzzles /
     identify). Reuses the generic helper modules (create-result, create-match,
     create-human-wait, human-games-registry) exposed on window.CVH — it does NOT
     load the page-specific create.js / create-human.js / puzzle-launcher.js. */

  var resultApi = window.CVH && window.CVH.createResult;
  var matchApi = window.CVH && window.CVH.createMatch;
  var waitApi = window.CVH && window.CVH.createHumanWait;
  var registry = window.CVH && window.CVH.humanGames;

  var VALID_FLOWS = ["engine", "avaa", "playground", "puzzles", "identify"];
  var REDIRECT_MS = 4000;

  var flow = "engine";
  var pairing = "find";
  var activeWaitPoll = null;
  var pollTimer = null;
  var activeLobbyId = null;
  var activeLobbyApiKey = null;

  var FLOW_META = {
    engine: { heading: "Create Game", card: "Rated game vs engine", submit: "Start game", aside: "engine" },
    avaa: { heading: "Agent vs Agent", card: "Two agents, one match", submit: "Start match", aside: "avaa" },
    playground: { heading: "Playground", card: "Unranked game vs human", submit: "Create unranked game", aside: "playground" },
    puzzles: { heading: "Puzzles", card: "Solve one puzzle for a vision agent", submit: "Start attempt", aside: "puzzles" },
    identify: { heading: "Board identification", card: "Name every occupied square for a vision agent", submit: "Start attempt", aside: "identify" },
  };

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

  function escapeHtml(value) {
    if (resultApi && resultApi.escapeHtml) return resultApi.escapeHtml(value);
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;");
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
      headers: { "content-type": "application/json", authorization: "Bearer " + apiKey },
      body: "{}",
    });
  }

  function createDirectAvaa(whiteKey, blackKey, whiteId, blackId) {
    return apiJson("/api/v1/games/agent-vs-agent", {
      method: "POST",
      headers: { "content-type": "application/json", authorization: "Bearer " + whiteKey },
      body: JSON.stringify({ white_model_id: whiteId, black_model_id: blackId, peer_api_key: blackKey }),
    });
  }

  function createHumanGame(apiKey, nickname) {
    var body = {};
    if (nickname) body.nickname = nickname;
    return apiJson("/api/v1/games/human", {
      method: "POST",
      headers: { "content-type": "application/json", authorization: "Bearer " + apiKey },
      body: JSON.stringify(body),
    });
  }

  function startAttempt(kind, apiKey) {
    var path = kind === "identify" ? "/api/v1/identify/start" : "/api/v1/puzzles/start";
    return apiJson(path, { method: "POST", headers: { authorization: "Bearer " + apiKey } });
  }

  function fillModelSelect(selectEl, agents, placeholder) {
    var html = '<option value="">' + escapeHtml(placeholder) + "</option>";
    agents.forEach(function (agent) {
      var id = agent.id || "";
      var label = agent.name && agent.name !== id ? agent.name + " (" + id + ")" : id;
      html += '<option value="' + escapeHtml(id) + '">' + escapeHtml(label) + "</option>";
    });
    selectEl.innerHTML = html;
  }

  function loadAgents(selects) {
    var list = Array.isArray(selects) ? selects : [selects];
    return apiJson("/api/v1/agents").then(function (data) {
      var agents = Array.isArray(data.agents) ? data.agents : [];
      list.forEach(function (selectEl) {
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

  function stopWaitPoll() {
    if (activeWaitPoll) {
      activeWaitPoll.stop();
      activeWaitPoll = null;
    }
  }

  function stopPoll() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function hideChrome(root) {
    var form = root.querySelector("[data-create-form]");
    if (form) form.hidden = true;
    root.querySelectorAll(".mode-tabs:not(.pairing-tabs)").forEach(function (el) {
      el.hidden = true;
    });
  }

  function resolveModelAndKey(selectEl, newModelId, newModelName) {
    var freshId = (newModelId && newModelId.value || "").trim();
    var modelId = (selectEl && selectEl.value || "").trim();
    var chosenId = freshId || modelId;
    if (!chosenId) {
      return Promise.reject(new Error("Select an inscribed model, or inscribe one below."));
    }
    return registerAgent(chosenId, freshId ? (newModelName && newModelName.value || undefined) : undefined).then(
      function (reg) {
        if (!reg.api_key) throw new Error("No API key returned.");
        return { apiKey: reg.api_key, modelId: reg.id || chosenId };
      }
    );
  }

  function resolveDirectPair(whiteSelect, blackSelect) {
    var w = (whiteSelect && whiteSelect.value || "").trim();
    var b = (blackSelect && blackSelect.value || "").trim();
    if (!w || !b) {
      return Promise.reject(new Error("Select both a white and a black model for Direct."));
    }
    return Promise.all([registerAgent(w), registerAgent(b)]).then(function (regs) {
      if (!regs[0].api_key || !regs[1].api_key) throw new Error("No API key returned.");
      return {
        whiteKey: regs[0].api_key,
        blackKey: regs[1].api_key,
        whiteId: regs[0].id || w,
        blackId: regs[1].id || b,
      };
    });
  }

  function saveHumanGame(game) {
    if (!registry) return;
    registry.upsert({
      gameId: game.game_id,
      token: game.play_token,
      nickname: game.human_nickname || "",
      agentName: game.model_display_name || game.model_name || "",
    });
  }

  function showHumanResult(root, game) {
    setMessage(messageEl, null, "");
    stopWaitPoll();
    saveHumanGame(game);
    hideChrome(root);
    resultEl.hidden = false;
    resultEl.innerHTML =
      '<div class="form-message form-message-ok">Game created. Copy the agent prompt below.</div>' +
      '<p class="game-id-line">Game ID: <code>' + escapeHtml(game.game_id) + "</code></p>" +
      '<p class="human-wait-status is-waiting" data-human-wait-status aria-live="polite">' +
      "<strong>Waiting for agent…</strong> Paste the brief into your agent. " +
      "You will be taken to the play board when the agent joins.</p>" +
      (resultApi && resultApi.renderBriefCollapsible
        ? resultApi.renderBriefCollapsible(game.agent_brief, escapeHtml)
        : "");
    if (resultApi && resultApi.wireCopyBrief) resultApi.wireCopyBrief(resultEl);
    if (!waitApi || !registry) return;
    var waitStatus = resultEl.querySelector("[data-human-wait-status]");
    activeWaitPoll = waitApi.startWaitingPoll(game.game_id, game.play_token, {
      onJoined: function () {
        location.replace(registry.playHref(game.game_id, game.play_token));
      },
      onGameOver: function () {
        registry.remove(game.game_id);
        if (waitStatus) {
          waitStatus.textContent = "Game ended before the agent joined.";
          waitStatus.classList.remove("is-waiting");
        }
      },
      onError: function () {
        /* keep polling */
      },
    });
  }

  function showPuzzleResult(root, kind, data, label) {
    stopWaitPoll();
    setMessage(messageEl, null, "");
    var attemptId = data.attempt_id;
    var watchPath = kind === "identify" ? "/i/" + attemptId : "/p/" + attemptId;
    hideChrome(root);
    resultEl.hidden = false;
    resultEl.innerHTML =
      '<div class="form-message form-message-ok">' +
      "<strong>" + escapeHtml(kind === "identify" ? "Board identification started" : "Puzzle started") + "</strong> · " +
      escapeHtml(label) +
      ' · <a href="/leaderboard/?tab=' + (kind === "identify" ? "identify" : "puzzles") + '">Leaderboard</a></div>' +
      '<p class="game-id-line">Attempt ID: <code>' + escapeHtml(attemptId) + "</code></p>" +
      (data.agent_brief
        ? resultApi.renderBriefCollapsible(data.agent_brief, escapeHtml)
        : '<p class="form-message form-message-error">No agent prompt was returned — check CHESS_HARNESS_PUBLIC_URL on the game PC.</p>') +
      '<p class="card-hint">Redirecting to the watch page…</p>';
    if (resultApi && resultApi.wireCopyBrief) resultApi.wireCopyBrief(resultEl);
    window.setTimeout(function () {
      window.location.assign(watchPath);
    }, REDIRECT_MS);
  }

  /* --- module-local refs, assigned in mount --- */
  var root, modelSelect, whiteSelect, blackSelect, newModelId, newModelName;
  var submitBtn, messageEl, inscribeBtn, resultEl, nicknameEl;
  var singleModelRow, directFields, pairingTabs, nicknameField;

  function setPairing(mode, messageEl) {
    pairing = mode === "direct" ? "direct" : "find";
    root.querySelectorAll("[data-launch-pairing]").forEach(function (tab) {
      var active = tab.getAttribute("data-launch-pairing") === pairing;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    if (directFields) directFields.hidden = pairing !== "direct";
    if (singleModelRow) singleModelRow.hidden = pairing === "direct";
    if (messageEl) setMessage(messageEl, null, "");
  }

  function setFlowId(name) {
    flow = VALID_FLOWS.indexOf(name) >= 0 ? name : "engine";
    var meta = FLOW_META[flow];

    root.querySelectorAll("[data-launch-flow]").forEach(function (tab) {
      var active = tab.getAttribute("data-launch-flow") === flow;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });

    var heading = root.querySelector("[data-launch-heading]");
    var cardHeading = root.querySelector("[data-launch-card-heading]");
    if (heading) heading.textContent = meta.heading;
    if (cardHeading) cardHeading.textContent = meta.card;
    if (submitBtn) submitBtn.textContent = meta.submit;

    root.querySelectorAll("[data-launch-aside-block]").forEach(function (block) {
      block.hidden = block.getAttribute("data-launch-aside-block") !== meta.aside;
    });

    var isAvaa = flow === "avaa";
    if (pairingTabs) pairingTabs.hidden = !isAvaa;
    if (nicknameField) nicknameField.hidden = flow !== "playground";

    if (isAvaa) {
      setPairing(pairing, messageEl);
    } else {
      if (directFields) directFields.hidden = true;
      if (singleModelRow) singleModelRow.hidden = false;
    }

    try {
      var url = new URL(window.location.href);
      url.searchParams.set("flow", flow);
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    } catch (e) {
      /* ignore */
    }
  }

  function parseFlowFromUrl() {
    var search = window.location.search || "";
    var m = search.match(/[?&]flow=([^&]+)/);
    return m ? decodeURIComponent(m[1]) : "engine";
  }

  function enableForm(online) {
    root.classList.toggle("create-online", online);
    var form = root.querySelector("[data-create-form]");
    if (form) form.hidden = !online;
    [modelSelect, whiteSelect, blackSelect, newModelId, newModelName, inscribeBtn].forEach(function (el) {
      if (el) el.disabled = !online;
    });
    if (submitBtn) submitBtn.disabled = !online;
  }

  function matchHelpers() {
    var self = this;
    return {
      stopPoll: stopPoll,
      beginWaiting: function (lobbyId, apiKey) {
        activeLobbyId = lobbyId;
        activeLobbyApiKey = apiKey;
        root.dataset.avaaWaiting = "1";
      },
      clearWaiting: function () {
        activeLobbyId = null;
        activeLobbyApiKey = null;
        delete root.dataset.avaaWaiting;
      },
      setMessage: setMessage,
      showResult: function (r, gameId, brief, matched, msgEl, options) {
        if (matched && resultApi) {
          resultApi.showBriefResult(r, gameId, brief, true, {
            escapeHtml: escapeHtml,
            autoRedirectMs: matchApi ? matchApi.MATCH_REDIRECT_MS : undefined,
          });
        }
      },
      schedule: function (fn, ms) {
        stopPoll();
        pollTimer = setTimeout(fn, ms);
      },
    };
  }

  function handleEngineSubmit() {
    return resolveModelAndKey(modelSelect, newModelId, newModelName)
      .then(function (ctx) { return createEngineGame(ctx.apiKey); })
      .then(function (game) {
        if (!resultApi) throw new Error("Result module missing.");
        var g = resultApi.requireBrief(game, false);
        resultApi.showBriefResult(root, g.game_id, g.agent_brief, false, { escapeHtml: escapeHtml });
      });
  }

  function handleAvaaSubmit() {
    if (pairing === "direct") {
      return resolveDirectPair(whiteSelect, blackSelect)
        .then(function (pair) {
          return createDirectAvaa(pair.whiteKey, pair.blackKey, pair.whiteId, pair.blackId);
        })
        .then(function (game) {
          if (!resultApi) throw new Error("Result module missing.");
          resultApi.showDualBriefResult(root, game, { escapeHtml: escapeHtml });
        });
    }
    return resolveModelAndKey(modelSelect, newModelId, newModelName)
      .then(function (ctx) {
        if (!matchApi) throw new Error("Matchmaking module missing.");
        activeLobbyApiKey = ctx.apiKey;
        return matchApi.findMatch(apiJson, ctx.apiKey).then(function (data) {
          matchApi.handleAvaaResponse(apiJson, root, data, ctx.apiKey, messageEl, matchHelpers());
        });
      });
  }

  function handlePlaygroundSubmit() {
    var nickname = (nicknameEl && nicknameEl.value || "").trim();
    return resolveModelAndKey(modelSelect, newModelId, newModelName)
      .then(function (ctx) { return createHumanGame(ctx.apiKey, nickname); })
      .then(function (game) { showHumanResult(root, game); });
  }

  function handlePuzzleSubmit() {
    var kind = flow === "identify" ? "identify" : "puzzles";
    var label =
      (modelSelect.selectedOptions[0] && modelSelect.selectedOptions[0].textContent) ||
      (modelSelect && modelSelect.value) || "";
    return resolveModelAndKey(modelSelect, newModelId, newModelName)
      .then(function (ctx) { return startAttempt(kind, ctx.apiKey); })
      .then(function (data) { showPuzzleResult(root, kind, data, label); });
  }

  function mountLauncher() {
    root = document.querySelector("[data-launch-page]");
    if (!root) return;

    modelSelect = root.querySelector("#model-select");
    whiteSelect = root.querySelector("#white-model-select");
    blackSelect = root.querySelector("#black-model-select");
    newModelId = root.querySelector("#new-model-id");
    newModelName = root.querySelector("#new-model-name");
    nicknameEl = root.querySelector("#human-nickname");
    submitBtn = root.querySelector("[data-launch-submit]");
    messageEl = root.querySelector("[data-create-message]");
    inscribeBtn = root.querySelector("[data-inscribe-submit]");
    resultEl = root.querySelector("[data-create-result]");
    pairingTabs = root.querySelector("[data-avaa-pairing-tabs]");
    singleModelRow = root.querySelector("[data-single-model-row]");
    directFields = root.querySelector("[data-avaa-direct-fields]");
    nicknameField = root.querySelector("[data-playground-nickname]");

    setFlowId(parseFlowFromUrl());

    window.CVH.applyHealthUi({
      onHealth: function (health) {
        enableForm(health.online);
        if (!health.online) return;
        loadAgents([modelSelect, whiteSelect, blackSelect]).catch(function (err) {
          setMessage(messageEl, "error", err.message || "Could not load models.");
        });
      },
    });

    root.querySelectorAll("[data-launch-flow]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        stopWaitPoll();
        stopPoll();
        if (root.dataset.avaaWaiting) {
          if (activeLobbyId && activeLobbyApiKey && matchApi) {
            matchApi.cancelLobby(apiJson, activeLobbyId, activeLobbyApiKey);
          }
          delete root.dataset.avaaWaiting;
        }
        resultEl.hidden = true;
        resultEl.innerHTML = "";
        setMessage(messageEl, null, "");
        setFlowId(tab.getAttribute("data-launch-flow"));
      });
    });

    root.querySelectorAll("[data-launch-pairing]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        setPairing(tab.getAttribute("data-launch-pairing"), messageEl);
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

    var form = root.querySelector("[data-create-form]");
    if (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        if (root.dataset.avaaWaiting) return;
        setMessage(messageEl, null, "");
        stopWaitPoll();
        stopPoll();
        submitBtn.disabled = true;
        resultEl.hidden = true;
        resultEl.innerHTML = "";
        setMessage(messageEl, "ok", "Starting…");

        if (flow === "avaa" && activeLobbyId && matchApi) {
          matchApi.cancelLobby(apiJson, activeLobbyId, activeLobbyApiKey).catch(function () {});
        }
        if (flow !== "avaa") delete root.dataset.avaaWaiting;

        var task;
        if (flow === "avaa") task = handleAvaaSubmit();
        else if (flow === "playground") task = handlePlaygroundSubmit();
        else if (flow === "puzzles" || flow === "identify") task = handlePuzzleSubmit();
        else task = handleEngineSubmit();

        task
          .catch(function (err) {
            setMessage(messageEl, "error", err.message || "Request failed.");
          })
          .finally(function () {
            if (!root.dataset.avaaWaiting && submitBtn) submitBtn.disabled = false;
          });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", mountLauncher);
})();
