/* Bounded, independent Ops requests. One in-flight request per URL/key. */
(function () {
  "use strict";
  var pending = new Map();
  function request(key, url, timeoutMs, options) {
    var identity = key + ":" + url;
    if (pending.has(identity)) return pending.get(identity);
    var controller = new AbortController();
    var timer;
    var deadline = new Promise(function (_resolve, reject) {
      timer = setTimeout(function () {
        controller.abort();
        reject(new Error("Request timed out; last successful data may be stale."));
      }, timeoutMs || 12000);
    });
    var operation = Promise.resolve().then(function () {
      return fetch(url, Object.assign({}, options, { cache: "no-store", signal: controller.signal }));
    }).then(function (res) {
      if (!res.ok) return res.json().catch(function () { return {}; }).then(function (body) {
        throw Object.assign(new Error(body.detail || "HTTP " + res.status + "; last successful data may be stale."), {status: res.status});
      });
      return res.json();
    });
    var result = Promise.race([operation, deadline]).finally(function () {
      clearTimeout(timer);
      pending.delete(identity);
    });
    pending.set(identity, result);
    return result;
  }
  window.CVH = window.CVH || {};
  window.CVH.opsRequest = request;
})();
