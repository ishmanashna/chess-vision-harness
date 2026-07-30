(function () {
  "use strict";

  var CONTACT_URL = "/api/contact";
  var INBOX_URL = "/api/contact/inbox";

  function isLoopbackHost() {
    var host = window.location.hostname;
    return (
      host === "127.0.0.1" ||
      host === "localhost" ||
      host === "::1" ||
      host === "[::1]"
    );
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setMessage(el, text, ok) {
    if (!el) return;
    if (!text) {
      el.hidden = true;
      el.textContent = "";
      el.classList.remove("form-message-ok", "form-message-error");
      return;
    }
    el.hidden = false;
    el.textContent = text;
    el.classList.toggle("form-message-ok", ok === true);
    el.classList.toggle("form-message-error", ok === false);
  }

  function formatWhen(iso) {
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      return d.toLocaleString(undefined, {
        dateStyle: "medium",
        timeStyle: "short",
      });
    } catch (_err) {
      return iso;
    }
  }

  function renderInbox(listEl, messages) {
    if (!messages.length) {
      listEl.innerHTML = '<p class="empty-state">No messages yet.</p>';
      return;
    }
    listEl.innerHTML = messages
      .map(function (msg) {
        var unread = msg.read !== true;
        return (
          '<article class="inbox-item' +
          (unread ? " is-unread" : "") +
          '" data-id="' +
          escapeHtml(msg.id) +
          '">' +
          '<header class="inbox-item-head">' +
          "<strong>" +
          escapeHtml(msg.sender || "—") +
          "</strong>" +
          '<time datetime="' +
          escapeHtml(msg.created_at || "") +
          '">' +
          escapeHtml(formatWhen(msg.created_at)) +
          "</time>" +
          "</header>" +
          '<p class="inbox-item-body">' +
          escapeHtml(msg.message || "") +
          "</p>" +
          '<div class="inbox-item-actions">' +
          (unread
            ? '<button type="button" class="btn btn-secondary" data-inbox-read>Mark read</button>'
            : "") +
          '<button type="button" class="btn btn-secondary" data-inbox-delete>Delete</button>' +
          "</div>" +
          "</article>"
        );
      })
      .join("");
  }

  function loadInbox(root) {
    var listEl = root.querySelector("[data-inbox-list]");
    var msgEl = root.querySelector("[data-inbox-message]");
    return fetch(INBOX_URL, { cache: "no-store" })
      .then(function (res) {
        return res.json().then(function (data) {
          return { res: res, data: data };
        });
      })
      .then(function (out) {
        if (!out.res.ok || !out.data || out.data.ok === false) {
          throw new Error((out.data && out.data.error) || "Could not load inbox");
        }
        renderInbox(listEl, out.data.messages || []);
        setMessage(msgEl, "", true);
      })
      .catch(function (err) {
        listEl.innerHTML = "";
        setMessage(msgEl, err.message || "Could not load inbox", false);
      });
  }

  function bindInboxActions(root) {
    var listEl = root.querySelector("[data-inbox-list]");
    var msgEl = root.querySelector("[data-inbox-message]");
    listEl.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-inbox-read], [data-inbox-delete]");
      if (!btn) return;
      var item = btn.closest("[data-id]");
      if (!item) return;
      var id = item.getAttribute("data-id");
      var isDelete = btn.hasAttribute("data-inbox-delete");
      var url = INBOX_URL + "/" + encodeURIComponent(id) + (isDelete ? "" : "/read");
      var method = isDelete ? "DELETE" : "POST";
      fetch(url, { method: method, cache: "no-store" })
        .then(function (res) {
          return res.json().then(function (data) {
            return { res: res, data: data };
          });
        })
        .then(function (out) {
          if (!out.res.ok || !out.data || out.data.ok === false) {
            throw new Error((out.data && out.data.error) || "Action failed");
          }
          return loadInbox(root);
        })
        .catch(function (err) {
          setMessage(msgEl, err.message || "Action failed", false);
        });
    });
  }

  function bindForm(root) {
    var form = root.querySelector("[data-contact-form]");
    var msgEl = root.querySelector("[data-contact-message]");
    var submit = root.querySelector("[data-contact-submit]");
    if (!form) return;
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var sender = (form.sender.value || "").trim();
      var message = (form.message.value || "").trim();
      if (!sender || !message) {
        setMessage(msgEl, "Sender and message are required.", false);
        return;
      }
      if (submit) submit.disabled = true;
      setMessage(msgEl, "", true);
      fetch(CONTACT_URL, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sender: sender, message: message }),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { res: res, data: data };
          });
        })
        .then(function (out) {
          if (!out.res.ok || !out.data || out.data.ok === false) {
            throw new Error((out.data && out.data.error) || "Send failed");
          }
          form.reset();
          setMessage(msgEl, "Message sent. Thanks!", true);
          if (isLoopbackHost()) loadInbox(root);
        })
        .catch(function (err) {
          setMessage(msgEl, err.message || "Send failed", false);
        })
        .finally(function () {
          if (submit) submit.disabled = false;
        });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-contact-page]");
    if (!root) return;
    bindForm(root);
    if (!isLoopbackHost()) return;
    var inbox = root.querySelector("[data-contact-inbox]");
    if (!inbox) return;
    inbox.hidden = false;
    bindInboxActions(root);
    loadInbox(root);
  });
})();
