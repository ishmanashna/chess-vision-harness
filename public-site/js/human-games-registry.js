(function () {
  "use strict";

  var STORAGE_KEY = "cvh-human-games";
  var MAX_GAMES = 50;

  function loadAll() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      var list = raw ? JSON.parse(raw) : [];
      return Array.isArray(list) ? list : [];
    } catch (_err) {
      return [];
    }
  }

  function saveAll(list) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
    } catch (_err) {
      /* ignore quota errors */
    }
  }

  function normalize(entry) {
    if (!entry || !entry.gameId || !entry.token) return null;
    return {
      gameId: String(entry.gameId),
      token: String(entry.token),
      nickname: entry.nickname ? String(entry.nickname) : "",
      agentName: entry.agentName ? String(entry.agentName) : "",
      createdAt: entry.createdAt || new Date().toISOString(),
    };
  }

  function upsert(entry) {
    var row = normalize(entry);
    if (!row) return;
    var list = loadAll().filter(function (g) {
      return g.gameId !== row.gameId;
    });
    list.unshift(row);
    if (list.length > MAX_GAMES) list = list.slice(0, MAX_GAMES);
    saveAll(list);
  }

  function remove(gameId) {
    if (!gameId) return;
    var list = loadAll().filter(function (g) {
      return g.gameId !== String(gameId);
    });
    saveAll(list);
  }

  function get(gameId) {
    var id = String(gameId || "");
    return (
      loadAll().find(function (g) {
        return g.gameId === id;
      }) || null
    );
  }

  function playHref(gameId, token) {
    return (
      "/play/" +
      encodeURIComponent(gameId) +
      "?token=" +
      encodeURIComponent(token || "")
    );
  }

  function sorted() {
    return loadAll().slice().sort(function (a, b) {
      var ta = Date.parse(a.createdAt) || 0;
      var tb = Date.parse(b.createdAt) || 0;
      return tb - ta;
    });
  }

  window.CVH = window.CVH || {};
  window.CVH.humanGames = {
    STORAGE_KEY: STORAGE_KEY,
    loadAll: loadAll,
    upsert: upsert,
    remove: remove,
    get: get,
    playHref: playHref,
    sorted: sorted,
  };
})();
