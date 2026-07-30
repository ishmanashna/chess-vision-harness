(function () {
  "use strict";

  var MATCH_REDIRECT_MS = 1500;
  var POLL_INTERVAL_MS = 3000;
  var POLL_RETRY_MS = 3000;

  function findMatch(apiJson, apiKey) {
    return apiJson("/api/v1/lobbies", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + apiKey,
      },
      body: "{}",
    });
  }

  function cancelLobby(apiJson, lobbyId, apiKey) {
    return apiJson("/api/v1/lobbies/" + encodeURIComponent(lobbyId), {
      method: "DELETE",
      headers: { authorization: "Bearer " + apiKey },
    }).catch(function () {
      /* best-effort cancel */
    });
  }

  function isTransientPollError(err) {
    if (!err || !err.status) return true;
    return err.status >= 500 || err.status === 429;
  }

  function pollLobby(apiJson, root, lobbyId, apiKey, messageEl, helpers) {
    helpers.stopPoll();
    helpers.beginWaiting(lobbyId, apiKey);
    helpers.setMessage(messageEl, "ok", "Waiting for an opponent…");

    function tick() {
      apiJson("/api/v1/lobbies/" + encodeURIComponent(lobbyId), {
        headers: { authorization: "Bearer " + apiKey },
      })
        .then(function (data) {
          if (data.status === "matched" && data.game_id && data.agent_brief) {
            helpers.stopPoll();
            helpers.clearWaiting();
            helpers.showResult(root, data.game_id, data.agent_brief, true, messageEl, {
              autoRedirectMs: MATCH_REDIRECT_MS,
            });
            return;
          }
          helpers.schedule(tick, POLL_INTERVAL_MS);
        })
        .catch(function (err) {
          if (isTransientPollError(err)) {
            helpers.schedule(tick, POLL_RETRY_MS);
            return;
          }
          helpers.stopPoll();
          helpers.clearWaiting();
          helpers.setMessage(messageEl, "error", err.message || "Matchmaking poll failed.");
        });
    }

    tick();
  }

  function handleAvaaResponse(apiJson, root, data, apiKey, messageEl, helpers) {
    if (data.status === "matched" && data.game_id && data.agent_brief) {
      helpers.clearWaiting();
      helpers.showResult(root, data.game_id, data.agent_brief, true, messageEl, {
        autoRedirectMs: MATCH_REDIRECT_MS,
      });
      return;
    }
    if (data.status === "waiting" && data.lobby_id) {
      pollLobby(apiJson, root, data.lobby_id, apiKey, messageEl, helpers);
      return;
    }
    helpers.clearWaiting();
    throw new Error("Unexpected matchmaking response.");
  }

  window.CVH = window.CVH || {};
  window.CVH.createMatch = {
    findMatch: findMatch,
    cancelLobby: cancelLobby,
    handleAvaaResponse: handleAvaaResponse,
    MATCH_REDIRECT_MS: MATCH_REDIRECT_MS,
  };
})();
