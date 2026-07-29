(function () {
  "use strict";

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

  function isHumanMode(mode) {
    return mode === "human";
  }

  function parseModeFromUrl() {
    var search = window.location.search || "";
    if (search.indexOf("mode=avaa") >= 0) return "avaa";
    if (search.indexOf("mode=human") >= 0 || search.indexOf("mode=avh") >= 0) return "human";
    return "engine";
  }

  function updateUrlMode(mode) {
    try {
      var url = new URL(window.location.href);
      if (mode === "avaa") url.searchParams.set("mode", "avaa");
      else if (mode === "human") url.searchParams.set("mode", "human");
      else url.searchParams.delete("mode");
      window.history.replaceState({}, "", url.pathname + url.search + url.hash);
    } catch (e) {
      /* ignore */
    }
  }

  function modeLabels(mode) {
    if (mode === "avaa") return { heading: "Rated game vs agent", submit: "Find match" };
    if (mode === "human") {
      return { heading: "Unranked game vs human", submit: "Create unranked game" };
    }
    return { heading: "Rated game vs engine", submit: "Create rated game" };
  }

  function toggleHumanChrome(root, mode) {
    var labels = modeLabels(mode);
    var heading = root.querySelector("[data-mode-heading]");
    var submit = root.querySelector("[data-create-submit]");
    var asideEngine = root.querySelector("[data-aside-engine]");
    var asideAvaa = root.querySelector("[data-aside-avaa]");
    var asideHuman = root.querySelector("[data-aside-human]");
    var nicknameRow = root.querySelector("[data-nickname-row]");
    if (heading) heading.textContent = labels.heading;
    if (submit) submit.textContent = labels.submit;
    if (asideEngine) asideEngine.hidden = mode !== "engine";
    if (asideAvaa) asideAvaa.hidden = mode !== "avaa";
    if (asideHuman) asideHuman.hidden = mode !== "human";
    if (nicknameRow) nicknameRow.hidden = mode !== "human";
  }

  function showBriefResult(root, gameId, brief, matched, escapeHtml, extraHtml) {
    var result = root.querySelector("[data-create-result]");
    var form = root.querySelector("[data-create-form]");
    var tabs = root.querySelector(".mode-tabs");
    if (form) form.hidden = true;
    if (tabs) tabs.hidden = true;
    if (!result) return;
    result.hidden = false;
    result.innerHTML =
      '<div class="form-message form-message-ok">' +
      (matched ? "Matched. " : "Game created. ") +
      '<a href="/g/' +
      escapeHtml(gameId) +
      '">Spectate this game</a>' +
      ' · <a href="/spectator/">Spectator</a></div>' +
      '<p class="game-id-line">Game ID: <code>' +
      escapeHtml(gameId) +
      "</code></p>" +
      (extraHtml || "") +
      '<div class="brief-wrap">' +
      '<label for="agent-brief"><strong>Agent prompt</strong> — paste into your agent</label>' +
      '<textarea id="agent-brief" readonly rows="18">' +
      escapeHtml(brief) +
      "</textarea>" +
      '<button type="button" class="btn btn-secondary" data-copy-brief>Copy prompt</button></div>';
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

  function showHumanResult(root, gameId, brief, playToken, escapeHtml) {
    var playHref =
      "/play/" + encodeURIComponent(gameId) + "?token=" + encodeURIComponent(playToken || "");
    showBriefResult(
      root,
      gameId,
      brief,
      false,
      escapeHtml,
      '<p class="play-link-line"><a class="btn btn-primary" href="' +
        escapeHtml(playHref) +
        '">Open play board</a></p>'
    );
  }

  window.CVH = window.CVH || {};
  window.CVH.createHuman = {
    createHumanGame: createHumanGame,
    parseModeFromUrl: parseModeFromUrl,
    updateUrlMode: updateUrlMode,
    toggleHumanChrome: toggleHumanChrome,
    showBriefResult: showBriefResult,
    showHumanResult: showHumanResult,
    requireBrief: requireBrief,
    isHumanMode: isHumanMode,
  };
})();
