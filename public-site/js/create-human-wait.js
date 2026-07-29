(function () {
  "use strict";

  var POLL_MS = 2500;

  function fetchPosition(gameId, token) {
    return fetch("/api/play/" + encodeURIComponent(gameId) + "/position", {
      headers: { Authorization: "Bearer " + token },
    }).then(function (res) {
      return res.json().then(function (body) {
        if (!res.ok || body.ok === false) {
          var err = new Error((body && body.error) || "Could not load position");
          err.status = res.status;
          throw err;
        }
        return body;
      });
    });
  }

  function startWaitingPoll(gameId, token, callbacks) {
    var stopped = false;
    var timer = null;
    callbacks = callbacks || {};

    function stop() {
      stopped = true;
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
    }

    function schedule() {
      if (stopped) return;
      timer = setTimeout(pollOnce, POLL_MS);
    }

    function pollOnce() {
      if (stopped) return;
      fetchPosition(gameId, token)
        .then(function (pos) {
          if (stopped) return;
          if (pos.game_over) {
            stop();
            if (callbacks.onGameOver) callbacks.onGameOver(pos);
            return;
          }
          if (pos.agent_joined) {
            stop();
            if (callbacks.onJoined) callbacks.onJoined(pos);
            return;
          }
          schedule();
        })
        .catch(function (err) {
          if (stopped) return;
          if (callbacks.onError) callbacks.onError(err);
          schedule();
        });
    }

    pollOnce();
    return { stop: stop };
  }

  window.CVH = window.CVH || {};
  window.CVH.createHumanWait = {
    fetchPosition: fetchPosition,
    startWaitingPoll: startWaitingPoll,
  };
})();
