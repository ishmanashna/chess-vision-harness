/**
 * Localhost puzzle-set preview: board, solution line, and identify placement.
 */
(function () {
  "use strict";

  function escHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function puzzleIdFromPage() {
    var body = document.body;
    if (body && body.getAttribute("data-puzzle-id")) {
      return body.getAttribute("data-puzzle-id");
    }
    var parts = window.location.pathname.replace(/\/+$/, "").split("/");
    return parts[parts.length - 1] || "";
  }

  function fmtSide(side) {
    if (!side) return "—";
    return side === "white" ? "White" : "Black";
  }

  function placementRows(placement) {
    return Object.keys(placement || {})
      .sort()
      .map(function (square) {
        return { square: square, piece: placement[square] };
      });
  }

  function renderPlacement(root, placement) {
    var host = root.querySelector("[data-preview-placement]");
    if (!host) return;
    var rows = placementRows(placement);
    if (!rows.length) {
      host.innerHTML = '<p class="card-hint">No placement data.</p>';
      return;
    }
    host.innerHTML =
      '<table class="results-table"><thead><tr><th>Square</th><th>Piece</th></tr></thead><tbody>' +
      rows
        .map(function (row) {
          return (
            "<tr><td>" +
            escHtml(row.square) +
            "</td><td>" +
            escHtml(row.piece) +
            "</td></tr>"
          );
        })
        .join("") +
      "</tbody></table>";
  }

  function renderMeta(root, data) {
    var meta = root.querySelector("[data-preview-meta]");
    if (!meta) return;
    meta.innerHTML =
      "<dt>Puzzle</dt><dd><code>" +
      escHtml(data.id) +
      "</code></dd>" +
      "<dt>Difficulty</dt><dd>" +
      (data.difficulty != null ? escHtml(data.difficulty) : "—") +
      "</dd>" +
      "<dt>Side to move</dt><dd>" +
      escHtml(fmtSide(data.side_to_move)) +
      "</dd>" +
      "<dt>Themes</dt><dd>" +
      escHtml(data.themes || "—") +
      "</dd>";
  }

  function renderSolution(root, moves) {
    var host = root.querySelector("[data-preview-solution]");
    if (!host) return;
    if (!moves || !moves.length) {
      host.textContent = "No solution line recorded.";
      return;
    }
    host.textContent = moves.join(" ");
  }

  function showError(root, message) {
    var el = root.querySelector("[data-preview-error]");
    if (!el) return;
    if (message) {
      el.textContent = message;
      el.hidden = false;
    } else {
      el.textContent = "";
      el.hidden = true;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-puzzle-set-preview]");
    if (!root) return;
    var puzzleId = puzzleIdFromPage();
    if (!puzzleId) {
      showError(root, "Missing puzzle id in URL.");
      return;
    }

    fetch("/api/puzzle-set/" + encodeURIComponent(puzzleId) + "/preview")
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Preview unavailable (" + response.status + ")");
        }
        return response.json();
      })
      .then(function (data) {
        showError(root, "");
        document.title = "Puzzle " + data.id + " — Chess Vision Harness";
        renderMeta(root, data);
        renderSolution(root, data.solution_moves || []);
        renderPlacement(root, data.placement || {});
        var board = root.querySelector("[data-preview-board]");
        if (board && data.board_url) {
          board.src = data.board_url + "?v=" + Date.now();
          board.alt = "Puzzle position for " + data.id;
        }
      })
      .catch(function (err) {
        showError(root, err && err.message ? err.message : "Could not load preview.");
      });
  });
})();
