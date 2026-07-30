(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatQualityMean(value, suffix) {
    if (window.CVH && typeof window.CVH.formatQualityMean === "function") {
      return window.CVH.formatQualityMean(value, suffix);
    }
    if (value == null || value === "") return "—";
    var n = Number(value);
    if (isNaN(n)) return "—";
    if (suffix) return String(n) + suffix;
    return String(Math.round(n));
  }

  function renderEngineRows(opponents) {
    var list = Array.isArray(opponents) ? opponents.slice() : [];
    // Floaters first (Accuracy + Estimated Elo), then anchors by Elo.
    list.sort(function (a, b) {
      var aAnchor = a.anchor ? 1 : 0;
      var bAnchor = b.anchor ? 1 : 0;
      if (aAnchor !== bAnchor) return aAnchor - bAnchor;
      return (Number(b.elo) || 0) - (Number(a.elo) || 0);
    });
    if (!list.length) {
      return (
        '<tr><td colspan="6" class="empty-state">No engine ratings on the ladder yet.</td></tr>'
      );
    }
    return list
      .map(function (row, index) {
        var kind = row.anchor
          ? "Anchor"
          : row.uncalibrated
            ? "Uncalibrated"
            : "Calibrated";
        return (
          "<tr>" +
          '<td class="rank">' +
          (index + 1) +
          "</td>" +
          "<td>" +
          escapeHtml(row.name || row.id || "—") +
          "</td>" +
          '<td class="elo">' +
          escapeHtml(row.elo != null ? String(row.elo) : "—") +
          "</td>" +
          "<td>" +
          escapeHtml(formatQualityMean(row.mean_accuracy, "%")) +
          "</td>" +
          '<td title="Estimated strength from move accuracy via the calibration accuracy→Elo table — not ladder Elo.">' +
          escapeHtml(formatQualityMean(row.mean_play_rating)) +
          "</td>" +
          "<td>" +
          escapeHtml(kind) +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function mountEnginesTable(container) {
    var fetchLb =
      window.CVH && window.CVH.fetchLeaderboard
        ? window.CVH.fetchLeaderboard
        : function () {
            return fetch("/data/leaderboard.json", { cache: "no-cache" }).then(
              function (res) {
                if (!res.ok) throw new Error("leaderboard fetch failed");
                return res.json();
              }
            );
          };
    fetchLb()
      .then(function (data) {
        var tbody = container.querySelector("tbody");
        if (!tbody) return;
        tbody.innerHTML = renderEngineRows(data.opponents || []);
      })
      .catch(function () {
        var tbody = container.querySelector("tbody");
        if (tbody) {
          tbody.innerHTML =
            '<tr><td colspan="6" class="empty-state">Could not load engine ladder.</td></tr>';
        }
      });
  }

  window.CVH = window.CVH || {};
  window.CVH.mountEnginesTable = mountEnginesTable;
})();
