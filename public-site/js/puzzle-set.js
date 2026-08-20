/**
 * Localhost puzzle-set panel: summary chips + sortable table from GET /api/puzzle-set.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "chess-harness-puzzle-set-sort";
  var BAND_RANGES = {
    under_600: [null, 600],
    "600_800": [600, 800],
    "800_1000": [800, 1000],
    "1000_1200": [1000, 1200],
    "1200_1500": [1200, 1500],
    "1500_plus": [1500, null],
  };

  function fmtPct(value) {
    if (value == null || value === "") return "—";
    return (Number(value) * 100).toFixed(1) + "%";
  }

  function fmtSide(side) {
    if (!side) return "—";
    return side === "white" ? "White" : "Black";
  }

  function bandLabel(key) {
    var labels = {
      under_600: "Under 600",
      "600_800": "600–800",
      "800_1000": "800–1000",
      "1000_1200": "1000–1200",
      "1200_1500": "1200–1500",
      "1500_plus": "1500+",
    };
    return labels[key] || key;
  }

  function inBand(difficulty, bandKey) {
    if (!bandKey) return true;
    var range = BAND_RANGES[bandKey];
    if (!range) return true;
    var rating = Number(difficulty);
    if (isNaN(rating)) return false;
    if (range[0] != null && rating < range[0]) return false;
    if (range[1] != null && rating >= range[1]) return false;
    return true;
  }

  function renderSummary(root, summary, datasetVersion) {
    var chips = root.querySelector("[data-summary-chips]");
    if (!chips || !summary) return;
    var buckets = summary.buckets || {};
    var side = summary.side_to_move || {};
    var items = [
      { label: "Puzzles", value: String(summary.total || 0) },
      {
        label: "Rating",
        value:
          (summary.rating_min != null ? summary.rating_min : "—") +
          " – " +
          (summary.rating_max != null ? summary.rating_max : "—") +
          " (med " +
          (summary.rating_median != null ? summary.rating_median : "—") +
          ")",
      },
      { label: "Mean", value: summary.rating_mean != null ? String(summary.rating_mean) : "—" },
      { label: "White to move", value: String(side.white || 0) },
      { label: "Black to move", value: String(side.black || 0) },
      { label: "Never attempted", value: String(summary.never_attempted || 0) },
    ];
    Object.keys(buckets).forEach(function (key) {
      items.push({ label: bandLabel(key), value: String(buckets[key] || 0) });
    });
    chips.innerHTML = items
      .map(function (item) {
        return (
          '<li class="puzzle-set-chip"><span class="puzzle-set-chip-label">' +
          item.label +
          '</span> <strong>' +
          item.value +
          "</strong></li>"
        );
      })
      .join("");
    var meta = root.querySelector("[data-puzzle-set-meta]");
    if (meta) {
      meta.textContent = datasetVersion ? "Dataset " + datasetVersion : "";
    }
    root.querySelector("[data-puzzle-set-summary]").hidden = false;
    root.querySelector("[data-puzzle-set-controls]").hidden = false;
  }

  function identifyCell(row) {
    if (!row.identify_attempts) return "—";
    if (row.identify_full_rate != null && row.identify_full_rate >= 1) {
      return "100% board";
    }
    if (row.identify_mean_accuracy != null) {
      return fmtPct(row.identify_mean_accuracy);
    }
    return "—";
  }

  function watchLinks(row) {
    var links = [
      '<a href="/puzzle-set/' + encodeURIComponent(row.id) + '">Preview</a>',
    ];
    if (row.watch_puzzle) {
      links.push('<a href="' + row.watch_puzzle + '">Pz</a>');
    }
    if (row.watch_identify) {
      links.push('<a href="' + row.watch_identify + '">Id</a>');
    }
    return links.join(" · ");
  }

  function renderTable(table, rows, sortKey, sortDir) {
    var sort = window.CVH && window.CVH.tableSort;
    if (!sort) return;
    var sorted = sort.sortRows(rows, sortKey, sortDir, {
      numericKeys: [
        "difficulty",
        "puzzle_attempts",
        "puzzle_solves",
        "puzzle_solve_rate",
        "identify_attempts",
        "identify_mean_accuracy",
        "identify_full_rate",
      ],
      tieKey: "id",
    });
    var tbody = table.querySelector("tbody");
    if (!sorted.length) {
      tbody.innerHTML =
        '<tr><td colspan="10" class="empty-state">No puzzles match this filter.</td></tr>';
      return;
    }
    tbody.innerHTML = sorted
      .map(function (row, index) {
        return (
          "<tr>" +
          "<td>" +
          (index + 1) +
          "</td>" +
          '<td><code class="meta-attempt-id">' +
          row.id +
          "</code></td>" +
          "<td>" +
          (row.difficulty != null ? row.difficulty : "—") +
          "</td>" +
          "<td>" +
          fmtSide(row.side_to_move) +
          "</td>" +
          '<td title="' +
          (row.themes || "").replace(/"/g, "&quot;") +
          '">' +
          (row.themes || "—") +
          "</td>" +
          "<td>" +
          row.puzzle_attempts +
          "/" +
          row.puzzle_solves +
          "</td>" +
          "<td>" +
          fmtPct(row.puzzle_solve_rate) +
          "</td>" +
          "<td>" +
          row.identify_attempts +
          "</td>" +
          "<td>" +
          identifyCell(row) +
          "</td>" +
          "<td>" +
          watchLinks(row) +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
    sort.paintHeaders(table, sortKey, sortDir);
  }

  function showError(root, message) {
    var el = root.querySelector("[data-puzzle-set-error]");
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
    var root = document.querySelector("[data-puzzle-set-page]");
    if (!root) return;
    var table = root.querySelector("[data-puzzle-set-table]");
    var sort = window.CVH && window.CVH.tableSort;
    if (!table || !sort) return;

    var state = sort.loadState(STORAGE_KEY, { key: "difficulty", dir: "asc" });
    var allRows = [];
    var bandKey = "";

    function filteredRows() {
      return allRows.filter(function (row) {
        return inBand(row.difficulty, bandKey);
      });
    }

    function repaint() {
      renderTable(table, filteredRows(), state.key, state.dir);
    }

    sort.bindHeaders(table, {
      getKey: function () {
        return state.key;
      },
      getDir: function () {
        return state.dir;
      },
      setSort: function (key, dir) {
        state.key = key;
        state.dir = dir;
        sort.saveState(STORAGE_KEY, key, dir);
      },
      defaultDirForKey: function (key) {
        return key === "id" || key === "themes" || key === "side_to_move" ? "asc" : "desc";
      },
      onChange: repaint,
    });

    var bandSelect = root.querySelector("[data-rating-band]");
    if (bandSelect) {
      bandSelect.addEventListener("change", function () {
        bandKey = bandSelect.value || "";
        repaint();
      });
    }

    fetch("/api/puzzle-set")
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Puzzle set unavailable (" + response.status + ")");
        }
        return response.json();
      })
      .then(function (data) {
        showError(root, "");
        renderSummary(root, data.summary || {}, data.dataset_version);
        allRows = data.puzzles || [];
        repaint();
      })
      .catch(function (err) {
        showError(root, err && err.message ? err.message : "Could not load puzzle set.");
        var tbody = table.querySelector("tbody");
        if (tbody) {
          tbody.innerHTML =
            '<tr><td colspan="10" class="empty-state">Puzzle set unavailable on this host.</td></tr>';
        }
      });
  });
})();
