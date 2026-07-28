(function () {
  "use strict";

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

  function pollLobby(apiJson, root, lobbyId, apiKey, messageEl, helpers) {
    helpers.stopPoll();
    helpers.setMessage(messageEl, "ok", "Waiting for an opponent…");

    function tick() {
      apiJson("/api/v1/lobbies/" + encodeURIComponent(lobbyId), {
        headers: { authorization: "Bearer " + apiKey },
      })
        .then(function (data) {
          if (data.status === "matched" && data.game_id && data.agent_brief) {
            helpers.stopPoll();
            helpers.showResult(root, data.game_id, data.agent_brief, true);
            return;
          }
          helpers.schedule(tick, 3000);
        })
        .catch(function (err) {
          helpers.setMessage(messageEl, "error", err.message || "Matchmaking poll failed.");
        });
    }

    tick();
  }

  function handleAvaaResponse(apiJson, root, data, apiKey, messageEl, helpers) {
    if (data.status === "matched" && data.game_id && data.agent_brief) {
      helpers.showResult(root, data.game_id, data.agent_brief, true);
      return;
    }
    if (data.status === "waiting" && data.lobby_id) {
      pollLobby(apiJson, root, data.lobby_id, apiKey, messageEl, helpers);
      return;
    }
    throw new Error("Unexpected matchmaking response.");
  }

  window.CVH = window.CVH || {};
  window.CVH.createMatch = {
    findMatch: findMatch,
    handleAvaaResponse: handleAvaaResponse,
  };
})();
