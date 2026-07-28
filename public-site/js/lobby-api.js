(function () {
  "use strict";

  function apiJson(url, options) {
    return fetch(url, options).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var err = new Error((data && data.error) || "Request failed");
          err.status = res.status;
          err.payload = data;
          throw err;
        }
        return data;
      });
    });
  }

  function registerAgent(modelId, displayName) {
    var body = { id: modelId };
    if (displayName) body.name = displayName;
    return apiJson("/api/v1/agents", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  function loadAgents(selectEl, escapeHtml) {
    return apiJson("/api/v1/agents").then(function (data) {
      var agents = Array.isArray(data.agents) ? data.agents : [];
      var html = '<option value="">Select inscribed model…</option>';
      agents.forEach(function (agent) {
        var id = agent.id || "";
        var label = agent.name && agent.name !== id ? agent.name + " (" + id + ")" : id;
        html +=
          '<option value="' + escapeHtml(id) + '">' + escapeHtml(label) + "</option>";
      });
      selectEl.innerHTML = html;
      return agents;
    });
  }

  function loadLobbies(tableBody, escapeHtml) {
    return apiJson("/api/v1/lobbies").then(function (data) {
      var rows = Array.isArray(data.lobbies) ? data.lobbies : [];
      if (!rows.length) {
        tableBody.innerHTML =
          '<tr><td colspan="5" class="empty-state">No open lobbies. Create one or use Find match.</td></tr>';
        return rows;
      }
      tableBody.innerHTML = rows
        .map(function (lob) {
          return (
            "<tr>" +
            "<td>" +
            escapeHtml(lob.host_display_name || "—") +
            "</td>" +
            '<td class="elo">' +
            escapeHtml(String(lob.host_elo != null ? lob.host_elo : "—")) +
            "</td>" +
            "<td>" +
            escapeHtml(lob.color_offer || "random") +
            "</td>" +
            "<td>" +
            escapeHtml(lob.created || "") +
            "</td>" +
            '<td><button type="button" class="btn btn-secondary btn-sm" data-join-lobby="' +
            escapeHtml(lob.lobby_id || "") +
            '">Join</button></td>' +
            "</tr>"
          );
        })
        .join("");
      return rows;
    });
  }

  function postLobby(apiKey, body) {
    return apiJson("/api/v1/lobbies", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + apiKey,
      },
      body: JSON.stringify(body),
    });
  }

  function resolveModelAndKey(modelSelect, newModelId, newModelName) {
    var modelId = (modelSelect && modelSelect.value || "").trim();
    var freshId = (newModelId && newModelId.value || "").trim();
    var freshName = (newModelName && newModelName.value || "").trim();
    var chosenId = freshId || modelId;
    if (!chosenId) {
      return Promise.reject(new Error("Select an inscribed model, or inscribe a new one below."));
    }
    return registerAgent(chosenId, freshId ? freshName || undefined : undefined).then(function (reg) {
      if (!reg.api_key) throw new Error("No API key returned.");
      return { modelId: chosenId, apiKey: reg.api_key };
    });
  }

  window.CVH = window.CVH || {};
  window.CVH.lobbyApi = {
    apiJson: apiJson,
    registerAgent: registerAgent,
    loadAgents: loadAgents,
    loadLobbies: loadLobbies,
    postLobby: postLobby,
    resolveModelAndKey: resolveModelAndKey,
  };
})();
