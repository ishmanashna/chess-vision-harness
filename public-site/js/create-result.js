(function () {
  "use strict";

  var JOIN_POLL_MS = 2500;
  var activeJoinPoll = null;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function requireBrief(game, needToken) {
    if (!game.game_id) throw new Error("No game id returned.");
    if (!game.agent_brief) {
      throw new Error(
        "Server did not return agent_brief. Set CHESS_HARNESS_PUBLIC_URL on the game PC."
      );
    }
    if (needToken && !game.play_token) throw new Error("Server did not return play_token.");
    return game;
  }

  function wireCopyBrief(result) {
    result.querySelectorAll("[data-copy-brief]").forEach(function (copyBtn) {
      copyBtn.addEventListener("click", function () {
        var wrap = copyBtn.closest(".brief-wrap");
        var ta = wrap ? wrap.querySelector("textarea") : null;
        if (!ta) return;
        ta.select();
        navigator.clipboard.writeText(ta.value).catch(function () {
          document.execCommand("copy");
        });
      });
    });
  }

  function renderBriefCollapsible(brief, esc, options) {
    options = options || {};
    var label = options.label || "Show agent prompt";
    var copyLabel = options.copyLabel || "Copy prompt";
    var taId = options.textareaId || "agent-brief";
    // Copy stays outside <details> so it works without expanding the prompt.
    return (
      '<div class="brief-wrap">' +
      '<div class="brief-toolbar">' +
      (options.heading
        ? '<span class="brief-side-label">' + esc(options.heading) + "</span>"
        : "") +
      '<button type="button" class="btn btn-secondary" data-copy-brief>' +
      esc(copyLabel) +
      "</button>" +
      "</div>" +
      '<details class="brief-collapsible">' +
      "<summary>" +
      esc(label) +
      "</summary>" +
      '<textarea id="' +
      esc(taId) +
      '" readonly rows="18">' +
      esc(brief) +
      "</textarea>" +
      "</details></div>"
    );
  }

  function clearPendingMessage(root, selector) {
    var el = root.querySelector(selector);
    if (!el) return;
    el.hidden = true;
    el.textContent = "";
    el.className = "form-message";
  }

  function hideCreateChrome(root) {
    var form = root.querySelector("[data-create-form]");
    var tabs = root.querySelector(".mode-tabs:not(.pairing-tabs)");
    if (form) form.hidden = true;
    if (tabs) tabs.hidden = true;
  }

  function stopJoinPoll() {
    if (activeJoinPoll) {
      activeJoinPoll.stop();
      activeJoinPoll = null;
    }
  }

  function startJoinPoll(gameId, callbacks) {
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
      timer = setTimeout(pollOnce, JOIN_POLL_MS);
    }

    function pollOnce() {
      if (stopped) return;
      fetch("/api/games/" + encodeURIComponent(gameId) + "/state")
        .then(function (res) {
          return res.json().then(function (body) {
            if (!res.ok || body.ok === false) {
              var err = new Error((body && body.error) || "Could not load game state");
              err.status = res.status;
              throw err;
            }
            return body;
          });
        })
        .then(function (pos) {
          if (stopped) return;
          if (pos.game_over) {
            stop();
            if (callbacks.onGameOver) callbacks.onGameOver(pos);
            return;
          }
          if (callbacks.onProgress) callbacks.onProgress(pos);
          if (pos.white_joined && pos.black_joined) {
            stop();
            if (callbacks.onBothJoined) callbacks.onBothJoined(pos);
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

  function showBriefResult(root, gameId, brief, matched, options) {
    options = options || {};
    var esc = options.escapeHtml || escapeHtml;
    var extraHtml = options.extraHtml || "";
    stopJoinPoll();
    clearPendingMessage(root, "[data-create-message]");
    hideCreateChrome(root);
    var result = root.querySelector("[data-create-result]");
    if (!result) return;
    result.hidden = false;
    result.innerHTML =
      '<div class="form-message form-message-ok">' +
      (matched ? "Matched. " : "Game created. ") +
      '<a href="/g/' +
      esc(gameId) +
      '">Spectate this game</a>' +
      ' · <a href="/spectator/">Spectator</a></div>' +
      '<p class="game-id-line">Game ID: <code>' +
      esc(gameId) +
      "</code></p>" +
      extraHtml +
      renderBriefCollapsible(brief, esc);
    wireCopyBrief(result);
    if (matched && options.autoRedirectMs) {
      window.setTimeout(function () {
        window.location.assign("/g/" + gameId);
      }, options.autoRedirectMs);
    }
  }

  function joinStatusText(pos) {
    var w = pos && pos.white_joined;
    var b = pos && pos.black_joined;
    if (w && b) return "Both agents connected.";
    if (w && !b) return "White connected. Waiting for black…";
    if (!w && b) return "Black connected. Waiting for white…";
    return "Waiting for both agents to connect…";
  }

  function showDualBriefResult(root, game, options) {
    options = options || {};
    var esc = options.escapeHtml || escapeHtml;
    var gameId = game.game_id;
    var whiteBrief = game.white && game.white.agent_brief;
    var blackBrief = game.black && game.black.agent_brief;
    if (!gameId || !whiteBrief || !blackBrief) {
      throw new Error("Server did not return both agent briefs for Direct create.");
    }

    stopJoinPoll();
    clearPendingMessage(root, "[data-create-message]");
    hideCreateChrome(root);
    var result = root.querySelector("[data-create-result]");
    if (!result) return;

    var whiteLabel = (game.white && game.white.model_id) || "White";
    var blackLabel = (game.black && game.black.model_id) || "Black";

    result.hidden = false;
    result.innerHTML =
      '<div class="form-message form-message-ok">Direct game created. Copy both prompts below.</div>' +
      '<p class="game-id-line">Game ID: <code>' +
      esc(gameId) +
      "</code></p>" +
      '<p class="human-wait-status is-waiting" data-avaa-wait-status aria-live="polite">' +
      "<strong>Waiting for both agents…</strong> Paste each brief into its agent. " +
      "You will be taken to spectator when both have connected.</p>" +
      '<div class="dual-briefs">' +
      renderBriefCollapsible(whiteBrief, esc, {
        heading: "White — " + whiteLabel,
        label: "Show white prompt",
        copyLabel: "Copy white prompt",
        textareaId: "agent-brief-white",
      }) +
      renderBriefCollapsible(blackBrief, esc, {
        heading: "Black — " + blackLabel,
        label: "Show black prompt",
        copyLabel: "Copy black prompt",
        textareaId: "agent-brief-black",
      }) +
      "</div>";

    wireCopyBrief(result);

    var waitStatus = result.querySelector("[data-avaa-wait-status]");
    activeJoinPoll = startJoinPoll(gameId, {
      onProgress: function (pos) {
        if (!waitStatus) return;
        waitStatus.innerHTML =
          "<strong>" + esc(joinStatusText(pos)) + "</strong> Paste each brief into its agent.";
      },
      onBothJoined: function () {
        window.location.assign("/g/" + gameId);
      },
      onGameOver: function () {
        if (waitStatus) {
          waitStatus.textContent = "Game ended before both agents joined.";
          waitStatus.classList.remove("is-waiting");
        }
      },
      onError: function () {
        /* keep polling */
      },
    });
  }

  window.CVH = window.CVH || {};
  window.CVH.createResult = {
    escapeHtml: escapeHtml,
    requireBrief: requireBrief,
    showBriefResult: showBriefResult,
    showDualBriefResult: showDualBriefResult,
    wireCopyBrief: wireCopyBrief,
    renderBriefCollapsible: renderBriefCollapsible,
    stopJoinPoll: stopJoinPoll,
    startJoinPoll: startJoinPoll,
  };
})();
