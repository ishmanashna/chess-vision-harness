(function () {
  "use strict";

  var activeWaitPoll = null;

  function createHumanGame(apiJson, apiKey, nickname) {
    var body = {};
    if (nickname) body.nickname = nickname;
    return apiJson("/api/v1/games/human", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + apiKey,
      },
      body: JSON.stringify(body),
    });
  }

  function stopWaitPoll() {
    if (activeWaitPoll) {
      activeWaitPoll.stop();
      activeWaitPoll = null;
    }
  }

  function saveHumanGame(game) {
    var registry = window.CVH && window.CVH.humanGames;
    if (!registry) return;
    registry.upsert({
      gameId: game.game_id,
      token: game.play_token,
      nickname: game.human_nickname || "",
      agentName: game.model_display_name || game.model_name || "",
    });
    if (window.CVH.refreshHumanGamesLists) window.CVH.refreshHumanGamesLists();
  }

  function showHumanResult(root, game, escapeHtml) {
    var resultApi = window.CVH && window.CVH.createResult;
    var gameId = game.game_id;
    var brief = game.agent_brief;
    var playToken = game.play_token;
    var waitApi = window.CVH && window.CVH.createHumanWait;
    var registry = window.CVH && window.CVH.humanGames;

    stopWaitPoll();
    saveHumanGame(game);

    var result = root.querySelector("[data-create-result]");
    var form = root.querySelector("[data-create-form]") || root.querySelector("[data-human-form]");
    var tabs = root.querySelector(".mode-tabs");
    if (form) form.hidden = true;
    if (tabs) tabs.hidden = true;
    if (!result) return;

    result.hidden = false;
    result.innerHTML =
      '<div class="form-message form-message-ok">Game created. Copy the agent prompt below.</div>' +
      '<p class="game-id-line">Game ID: <code>' +
      escapeHtml(gameId) +
      "</code></p>" +
      '<p class="human-wait-status is-waiting" data-human-wait-status aria-live="polite">' +
      "<strong>Waiting for agent…</strong> Paste the brief into your agent. " +
      "You will be taken to the play board when the agent joins.</p>" +
      '<div class="brief-wrap">' +
      '<label for="agent-brief"><strong>Agent prompt</strong> — paste into your agent</label>' +
      '<textarea id="agent-brief" readonly rows="18">' +
      escapeHtml(brief) +
      "</textarea>" +
      '<button type="button" class="btn btn-secondary" data-copy-brief>Copy prompt</button></div>';

    if (resultApi && resultApi.wireCopyBrief) resultApi.wireCopyBrief(result);

    if (!waitApi || !registry) return;

    var waitStatus = result.querySelector("[data-human-wait-status]");
    activeWaitPoll = waitApi.startWaitingPoll(gameId, playToken, {
      onJoined: function () {
        location.replace(registry.playHref(gameId, playToken));
      },
      onGameOver: function () {
        registry.remove(gameId);
        if (window.CVH.refreshHumanGamesLists) window.CVH.refreshHumanGamesLists();
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

  window.CVH = window.CVH || {};
  window.CVH.createHuman = {
    createHumanGame: createHumanGame,
    showHumanResult: showHumanResult,
    stopWaitPoll: stopWaitPoll,
  };
})();
