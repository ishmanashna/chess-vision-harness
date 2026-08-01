/**
 * Shared sortable-table helpers for spectator games lists and leaderboard tables.
 *
 * Acc. / Performance: sort by the first numeric token in the value
 * (white side of "91.2% / 88.4%" or "1524 / 1498"; sole mean on the ladder).
 */
(function () {
  "use strict";

  function firstNumber(value) {
    if (value == null || value === "") return null;
    if (typeof value === "number" && !isNaN(value)) return value;
    var m = String(value).match(/-?\d+(?:\.\d+)?/);
    return m ? Number(m[0]) : null;
  }

  function sortRows(rows, key, dir, options) {
    options = options || {};
    var numericKeys = options.numericKeys || [];
    var tieKey = options.tieKey || "id";
    var mult = dir === "asc" ? 1 : -1;
    var isNumeric = numericKeys.indexOf(key) !== -1;

    return rows.slice().sort(function (a, b) {
      var va = a[key];
      var vb = b[key];
      if (isNumeric) {
        var na = firstNumber(va);
        var nb = firstNumber(vb);
        na = na == null ? -Infinity : na;
        nb = nb == null ? -Infinity : nb;
        if (na !== nb) return na < nb ? -mult : mult;
      } else {
        var sa = String(va == null ? "" : va).toLowerCase();
        var sb = String(vb == null ? "" : vb).toLowerCase();
        if (sa !== sb) return sa < sb ? -mult : mult;
      }
      var ta = a[tieKey];
      var tb = b[tieKey];
      return String(ta == null ? "" : ta).localeCompare(String(tb == null ? "" : tb)) * mult;
    });
  }

  function migrateKey(key, map) {
    if (map && Object.prototype.hasOwnProperty.call(map, key)) return map[key];
    return key;
  }

  function loadState(storageKey, defaults, migrateMap) {
    defaults = defaults || { key: null, dir: "asc" };
    try {
      var saved = JSON.parse(localStorage.getItem(storageKey) || "null");
      if (saved && saved.key) {
        return {
          key: migrateKey(saved.key, migrateMap),
          dir: saved.dir === "asc" ? "asc" : "desc",
        };
      }
    } catch (_err) {}
    return {
      key: defaults.key,
      dir: defaults.dir === "asc" ? "asc" : "desc",
    };
  }

  function saveState(storageKey, key, dir) {
    try {
      localStorage.setItem(storageKey, JSON.stringify({ key: key, dir: dir }));
    } catch (_err) {}
  }

  function paintHeaders(table, sortKey, sortDir) {
    if (!table) return;
    table.querySelectorAll("[data-sort]").forEach(function (th) {
      var key = th.getAttribute("data-sort");
      th.setAttribute(
        "aria-sort",
        key === sortKey ? (sortDir === "asc" ? "ascending" : "descending") : "none"
      );
      th.classList.toggle("is-sorted", key === sortKey);
    });
  }

  /**
   * Bind click-to-sort on [data-sort] headers.
   * options: getKey, getDir, setSort(key, dir), defaultDirForKey(key), onChange
   */
  function bindHeaders(table, options) {
    if (!table || !options) return;
    table.querySelectorAll("[data-sort]").forEach(function (th) {
      th.style.cursor = "pointer";
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (!key) return;
        var sortKey = options.getKey();
        var sortDir = options.getDir();
        if (sortKey === key) {
          sortDir = sortDir === "asc" ? "desc" : "asc";
        } else {
          sortKey = key;
          sortDir = options.defaultDirForKey
            ? options.defaultDirForKey(key)
            : "asc";
        }
        options.setSort(sortKey, sortDir);
        if (options.onChange) options.onChange();
      });
    });
  }

  window.CVH = window.CVH || {};
  window.CVH.tableSort = {
    firstNumber: firstNumber,
    sortRows: sortRows,
    loadState: loadState,
    saveState: saveState,
    paintHeaders: paintHeaders,
    bindHeaders: bindHeaders,
  };
})();
