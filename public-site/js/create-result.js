(function () {
  "use strict";

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
    var copyBtn = result.querySelector("[data-copy-brief]");
    if (!copyBtn) return;
    copyBtn.addEventListener("click", function () {
      var ta = document.getElementById("agent-brief");
      if (!ta) return;
      ta.select();
      navigator.clipboard.writeText(ta.value).catch(function () {
        document.execCommand("copy");
      });
    });
  }

  function showBriefResult(root, gameId, brief, matched, options) {
    options = options || {};
    var esc = options.escapeHtml || escapeHtml;
    var extraHtml = options.extraHtml || "";
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
      esc(gameId) +
      '">Spectate this game</a>' +
      ' · <a href="/spectator/">Spectator</a></div>' +
      '<p class="game-id-line">Game ID: <code>' +
      esc(gameId) +
      "</code></p>" +
      extraHtml +
      '<div class="brief-wrap">' +
      '<label for="agent-brief"><strong>Agent prompt</strong> — paste into your agent</label>' +
      '<textarea id="agent-brief" readonly rows="18">' +
      esc(brief) +
      "</textarea>" +
      '<button type="button" class="btn btn-secondary" data-copy-brief>Copy prompt</button></div>';
    wireCopyBrief(result);
  }

  window.CVH = window.CVH || {};
  window.CVH.createResult = {
    escapeHtml: escapeHtml,
    requireBrief: requireBrief,
    showBriefResult: showBriefResult,
    wireCopyBrief: wireCopyBrief,
  };
})();
