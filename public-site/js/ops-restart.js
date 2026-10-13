/* Local restart control: retain this page while the backend disconnects. */
(function () {
  "use strict";
  var pending = false, timer = null, deadline = 0, operation = null;
  function status(text) {
    var el = document.querySelector("[data-ops-restart-status]");
    if (el) el.textContent = text;
  }
  function controls(busy) {
    pending = busy;
    window.CVH.restartPending = busy;
    document.querySelectorAll("[data-ops-restart], [data-ops-go-online], [data-ops-sleep-public]").forEach(function (button) { button.disabled = busy; });
  }
  function finish(text) {
    if (timer) clearTimeout(timer);
    timer = null;
    controls(false);
    status(text);
  }
  function wait() {
    if (Date.now() >= deadline) return finish("Restart not confirmed. Check restart-server.log in the harness logs folder.");
    window.CVH.opsRequest("restart-status", "/api/ops/restart-server", 4000).then(function (row) {
      if (operation && row.operation_id !== operation) throw new Error("Waiting for requested restart");
      if (row.status === "ready" && row.new_pid === row.server_pid && row.old_instance !== row.instance) {
        finish("Server restarted successfully. Updated code is active.");
        return;
      }
      if (row.status === "fail") { finish("Restart failed: " + row.phase); return; }
      status(row.phase || "Restarting server; reconnecting...");
      timer = setTimeout(wait, 2000);
    }).catch(function () {
      status("Restarting server; reconnecting...");
      timer = setTimeout(wait, 2000);
    });
  }
  function start() {
    if (pending) return;
    controls(true);
    status("Checking for active work...");
    window.CVH.opsRequest("restart-start", "/api/ops/restart-server", 20000, {method:"POST"}).then(function (row) {
      operation = row.operation_id;
      deadline = Date.now() + 120000;
      status("Restarting server; this page will reconnect automatically.");
      timer = setTimeout(wait, 1000);
    }).catch(function (error) { finish(error.message); });
  }
  document.addEventListener("DOMContentLoaded", function () {
    var button = document.querySelector("[data-ops-restart]");
    if (!button) return;
    button.addEventListener("click", start);
    window.CVH.opsRequest("restart-status", "/api/ops/restart-server", 5000).then(function (row) {
      if (!row.supported) {
        button.disabled = true;
        status("Restart control requires managed chess-harness serve.");
      } else if (row.status === "restarting" || row.status === "starting") {
        controls(true); operation = row.operation_id; deadline = Date.now() + 120000; wait();
      } else if (row.status === "fail") status("Last restart failed: " + row.phase);
    }).catch(function (error) {
      button.disabled = true;
      status(error.status === 404 ? "One manual server restart is needed to activate this new control." : "Could not read restart status. Reload to retry.");
    });
  });
})();
