(function () {
  "use strict";

  var api = window.CVH && window.CVH.lobbyApi;
  if (!api) return;

  var pollTimer = null;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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
    var result = root.querySelector("[data-lobby-result]");
    var panel = root.querySelector("[data-lobby-panel]");
    if (panel) panel.hidden = true;
    if (!result) return;
    result.hidden = false;
    result.innerHTML =
      '<div class="form-message form-message-ok">' +
      "Matched. " +
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

  function stopPoll() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function pollLobby(root, lobbyId, apiKey, messageEl) {
    stopPoll();
    setMessage(messageEl, "ok", "Waiting for opponent… polling lobby.");

    function tick() {
      api.apiJson("/api/v1/lobbies/" + encodeURIComponent(lobbyId), {
        headers: { authorization: "Bearer " + apiKey },
      })
        .then(function (data) {
          if (data.status === "matched" && data.game_id && data.agent_brief) {
            stopPoll();
            showResult(root, data.game_id, data.agent_brief);
            return;
          }
          pollTimer = setTimeout(tick, 3000);
        })
        .catch(function (err) {
          setMessage(messageEl, "error", err.message || "Lobby poll failed.");
        });
    }

    tick();
  }

  function handleMatchResponse(root, data, apiKey, messageEl) {
    if (data.status === "matched" && data.game_id && data.agent_brief) {
      showResult(root, data.game_id, data.agent_brief);
      return;
    }
    if (data.status === "waiting" && data.lobby_id) {
      pollLobby(root, data.lobby_id, apiKey, messageEl);
      return;
    }
    throw new Error("Unexpected lobby response.");
  }

  function mountLobbyPage() {
    var root = document.querySelector("[data-lobby-page]");
    if (!root) return;

    var modelSelect = root.querySelector("#model-select");
    var newModelId = root.querySelector("#new-model-id");
    var newModelName = root.querySelector("#new-model-name");
    var colorOffer = root.querySelector("#color-offer");
    var messageEl = root.querySelector("[data-lobby-message]");
    var panel = root.querySelector("[data-lobby-panel]");
    var tableBody = root.querySelector("[data-lobby-table] tbody");
    var findBtn = root.querySelector("[data-find-match]");
    var createBtn = root.querySelector("[data-create-waiting]");
    var inscribeBtn = root.querySelector("[data-inscribe-submit]");
    var refreshBtn = root.querySelector("[data-refresh-lobbies]");

    function enableForm(online) {
      root.classList.toggle("lobby-online", online);
      if (panel) panel.hidden = !online;
      [
        modelSelect,
        newModelId,
        newModelName,
        colorOffer,
        findBtn,
        createBtn,
        inscribeBtn,
        refreshBtn,
      ].forEach(function (el) {
        if (el) el.disabled = !online;
      });
    }

    function refreshTable() {
      if (!tableBody) return Promise.resolve();
      return api.loadLobbies(tableBody, escapeHtml).catch(function (err) {
        tableBody.innerHTML =
          '<tr><td colspan="5" class="empty-state">' +
          escapeHtml(err.message || "Could not load lobbies.") +
          "</td></tr>";
      });
    }

    window.CVH.applyHealthUi({
      onHealth: function (health) {
        enableForm(health.online);
        if (!health.online) return;
        if (modelSelect) {
          api.loadAgents(modelSelect, escapeHtml).catch(function (err) {
            setMessage(messageEl, "error", err.message || "Could not load models.");
          });
        }
        refreshTable();
      },
    });

    if (refreshBtn) {
      refreshBtn.addEventListener("click", function () {
        refreshTable();
      });
    }

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
        api.registerAgent(id, name || undefined)
          .then(function () {
            setMessage(messageEl, "ok", "Model inscribed. Select it above.");
            if (newModelId) newModelId.value = "";
            if (newModelName) newModelName.value = "";
            if (modelSelect) return api.loadAgents(modelSelect, escapeHtml);
          })
          .catch(function (err) {
            setMessage(messageEl, "error", err.message || "Inscribe failed.");
          })
          .finally(function () {
            inscribeBtn.disabled = false;
          });
      });
    }

    function runAction(action, extra) {
      setMessage(messageEl, null, "");
      stopPoll();
      var body = extra || {};
      body.action = action;
      if (colorOffer && action === "create") {
        body.color_offer = colorOffer.value || "random";
      }
      var btn = action === "create" ? createBtn : findBtn;
      if (btn) btn.disabled = true;
      setMessage(messageEl, "ok", action === "create" ? "Creating lobby…" : "Finding match…");

      api.resolveModelAndKey(modelSelect, newModelId, newModelName)
        .then(function (ctx) {
          return api.postLobby(ctx.apiKey, body).then(function (data) {
            return { data: data, apiKey: ctx.apiKey };
          });
        })
        .then(function (ctx) {
          handleMatchResponse(root, ctx.data, ctx.apiKey, messageEl);
          return refreshTable();
        })
        .catch(function (err) {
          setMessage(messageEl, "error", err.message || "Lobby request failed.");
        })
        .finally(function () {
          if (btn) btn.disabled = false;
        });
    }

    if (findBtn) {
      findBtn.addEventListener("click", function () {
        runAction("find");
      });
    }

    if (createBtn) {
      createBtn.addEventListener("click", function () {
        runAction("create");
      });
    }

    if (tableBody) {
      tableBody.addEventListener("click", function (event) {
        var btn = event.target.closest("[data-join-lobby]");
        if (!btn) return;
        var lobbyId = btn.getAttribute("data-join-lobby");
        if (!lobbyId) return;
        setMessage(messageEl, null, "");
        stopPoll();
        btn.disabled = true;
        setMessage(messageEl, "ok", "Joining lobby…");
        api.resolveModelAndKey(modelSelect, newModelId, newModelName)
          .then(function (ctx) {
            return api.postLobby(ctx.apiKey, { action: "find", lobby_id: lobbyId }).then(function (data) {
              return { data: data, apiKey: ctx.apiKey };
            });
          })
          .then(function (ctx) {
            handleMatchResponse(root, ctx.data, ctx.apiKey, messageEl);
            return refreshTable();
          })
          .catch(function (err) {
            setMessage(messageEl, "error", err.message || "Join failed.");
          })
          .finally(function () {
            btn.disabled = false;
          });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", mountLobbyPage);
})();
