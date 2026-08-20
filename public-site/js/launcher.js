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
  var PUZZLE_WAIT_POLL_MS = 2500;

  var flow = "engine";
  var pairing = "find";
  var activeWaitPoll = null;
  var pollTimer = null;
  var activeLobbyId = null;
  var activeLobbyApiKey = null;
  var agentsForLoad = [];

  var FLOW_META = {
    engine: { heading: "Create Game", card: "Rated game vs engine", submit: "Start game", aside: "engine" },
    avaa: { heading: "Agent vs Agent", card: "Two agents, one match", submit: "Start match", aside: "avaa" },
    playground: { heading: "Playground", card: "Unranked game vs human", submit: "Create unranked game", aside: "playground" },
    puzzles: { heading: "Puzzles", card: "Solve one puzzle for your agent", submit: "Start attempt", aside: "puzzles" },
    identify: { heading: "Board identification", card: "Name every occupied square for your agent", submit: "Start attempt", aside: "identify" },
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

  var ID_SUFFIX_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789";

  function randomIdSuffix(len) {
    var out = "";
    for (var i = 0; i < len; i++) {
      out += ID_SUFFIX_CHARS.charAt(Math.floor(Math.random() * ID_SUFFIX_CHARS.length));
    }
    return out;
  }

  function slugify(value) {
    var slug = String(value)
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return slug || "model";
  }

  function generateModelId(displayName, occupied) {
    var base = slugify(displayName).slice(0, 32);
    var id;
    do {
      id = base + "-" + randomIdSuffix(6);
    } while (occupied.indexOf(id) >= 0);
    return id;
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
      agentsForLoad = agents.map(function (agent) { return agent.id || ""; });
      list.forEach(function (selectEl) {
        if (!selectEl) return;
        var placeholder =
          selectEl.id === "white-model-select"
            ? "Select white model…"
            : selectEl.id === "black-model-select"
              ? "Select black model…"
              : "Select your model…";
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
  }

  function resolveModelAndKey(selectEl) {
    var modelId = (selectEl && selectEl.value || "").trim();
    if (!modelId) {
      return Promise.reject(new Error("Select an inscribed model, or inscribe one below."));
    }
    return registerAgent(modelId).then(function (reg) {
      if (!reg.api_key) throw new Error("No API key returned.");
      return { apiKey: reg.api_key, modelId: reg.id || modelId };
    });
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
      (resultApi && resultApi.renderCopyIdRow ? resultApi.renderCopyIdRow() : "") +
      '<p class="human-wait-status is-waiting" data-human-wait-status aria-live="polite">' +
      "<strong>Waiting for agent…</strong> Paste the brief once. Your agent should keep polling, waiting, and moving with its own tools until the game ends. Do not re-prompt it. " +
      "You will be taken to the play board when the agent joins.</p>" +
      (resultApi && resultApi.renderBriefCollapsible
        ? resultApi.renderBriefCollapsible(game.agent_brief, escapeHtml)
        : "");
    if (resultApi && resultApi.wireCopyBrief) resultApi.wireCopyBrief(resultEl);
    if (resultApi && resultApi.wireCopyId) resultApi.wireCopyId(resultEl, game.game_id);
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
    var publicUrl =
      kind === "identify"
        ? "/api/v1/identify/public/" + encodeURIComponent(attemptId)
        : "/api/v1/puzzles/public/" + encodeURIComponent(attemptId);
    hideChrome(root);
    resultEl.hidden = false;
    resultEl.innerHTML =
      '<div class="form-message form-message-ok">' +
      "<strong>" + escapeHtml(kind === "identify" ? "Board identification started" : "Puzzle started") + "</strong> · " +
      escapeHtml(label) +
      ' · <a href="/leaderboard/">Leaderboards</a></div>' +
      (resultApi && resultApi.renderCopyIdRow ? resultApi.renderCopyIdRow() : "") +
      '<p class="human-wait-status is-waiting" data-puzzle-wait-status aria-live="polite">' +
      "<strong>Waiting for agent…</strong> Paste the brief once. The watch page opens when the agent reads the board. " +
      'You can also <a href="' + escapeHtml(watchPath) + '">open the watch page</a> manually.</p>' +
      (data.agent_brief
        ? resultApi.renderBriefCollapsible(data.agent_brief, escapeHtml)
        : '<p class="form-message form-message-error">No agent prompt was returned — check CHESS_HARNESS_PUBLIC_URL on the game PC.</p>');
    if (resultApi && resultApi.wireCopyBrief) resultApi.wireCopyBrief(resultEl);
    if (resultApi && resultApi.wireCopyId) resultApi.wireCopyId(resultEl, attemptId);
    var waitStatus = resultEl.querySelector("[data-puzzle-wait-status]");
    var stopped = false;
    var timer = null;

    function stopPoll() {
      stopped = true;
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    }

    function schedulePoll() {
      if (!stopped) timer = setTimeout(pollOnce, PUZZLE_WAIT_POLL_MS);
    }

    function pollOnce() {
      if (stopped) return;
      fetch(publicUrl)
        .then(function (res) {
          return res.json().then(function (body) {
            if (!res.ok) {
              var err = new Error((body && body.error) || "Could not load attempt state");
              err.status = res.status;
              throw err;
            }
            return body;
          });
        })
        .then(function (state) {
          if (stopped) return;
          if (state.agent_joined) {
            stopPoll();
            window.location.assign(watchPath);
            return;
          }
          if (state.status === "abandoned") {
            stopPoll();
            if (waitStatus) {
              waitStatus.innerHTML =
                "Attempt was abandoned (idle timeout). " +
                '<a href="' + escapeHtml(watchPath) + '">Open watch page</a>';
              waitStatus.classList.remove("is-waiting");
            }
            return;
          }
          if (state.status === "finished") {
            stopPoll();
            window.location.assign(watchPath);
            return;
          }
          schedulePoll();
        })
        .catch(function () {
          if (stopped) return;
          schedulePoll();
        });
    }

    activeWaitPoll = { stop: stopPoll };
    pollOnce();
  }

  /* --- module-local refs, assigned in mount --- */
  var root, modelSelect, whiteSelect, blackSelect, modeSelect, newModelName;
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

    if (modeSelect) modeSelect.value = flow;

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
    [modelSelect, whiteSelect, blackSelect, newModelName, inscribeBtn, nicknameEl].forEach(function (el) {
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
    return resolveModelAndKey(modelSelect)
      .then(function (ctx) { return createEngineGame(ctx.apiKey); })
      .then(function (game) {
        if (!resultApi) throw new Error("Result module missing.");
        var g = resultApi.requireBrief(game, false);
        resultApi.showBriefResult(root, g.game_id, g.agent_brief, false, {
          escapeHtml: escapeHtml,
          waitForAgent: true,
        });
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
    return resolveModelAndKey(modelSelect)
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
    return resolveModelAndKey(modelSelect)
      .then(function (ctx) { return createHumanGame(ctx.apiKey, nickname); })
      .then(function (game) { showHumanResult(root, game); });
  }

  function handlePuzzleSubmit() {
    var kind = flow === "identify" ? "identify" : "puzzles";
    var label =
      (modelSelect.selectedOptions[0] && modelSelect.selectedOptions[0].textContent) ||
      (modelSelect && modelSelect.value) || "";
    return resolveModelAndKey(modelSelect)
      .then(function (ctx) { return startAttempt(kind, ctx.apiKey); })
      .then(function (data) { showPuzzleResult(root, kind, data, label); });
  }

  function mountLauncher() {
    root = document.querySelector("[data-launch-page]");
    if (!root) return;

    modelSelect = root.querySelector("#model-select");
    whiteSelect = root.querySelector("#white-model-select");
    blackSelect = root.querySelector("#black-model-select");
    modeSelect = root.querySelector("[data-launch-mode]");
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

    root.querySelectorAll("[data-launch-mode]").forEach(function (selectEl) {
      selectEl.addEventListener("change", function () {
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
        setFlowId(selectEl.value);
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
        var name = (newModelName && newModelName.value || "").trim();
        if (!name) {
          setMessage(messageEl, "error", "Enter a display name.");
          return;
        }
        var id = generateModelId(name, agentsForLoad);
        inscribeBtn.disabled = true;
        registerAgent(id, name)
          .then(function () {
            setMessage(messageEl, "ok", "Model inscribed as " + id + " and selected below.");
            if (newModelName) newModelName.value = "";
            return loadAgents([modelSelect, whiteSelect, blackSelect]);
          })
          .then(function () {
            [modelSelect, whiteSelect, blackSelect].forEach(function (sel) {
              if (sel && sel.querySelector('option[value="' + id + '"]')) sel.value = id;
            });
            if (nicknameEl) nicknameEl.disabled = false;
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
