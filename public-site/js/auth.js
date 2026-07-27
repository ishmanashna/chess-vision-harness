(function () {
  "use strict";

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function displayName(user) {
    if (user && user.name) return user.name;
    if (user && user.email) return user.email;
    return "";
  }

  function ensureAuthRoot(controls) {
    var existing = controls.querySelector("[data-auth-root]");
    if (existing) return existing;
    var root = document.createElement("span");
    root.className = "auth-root";
    root.setAttribute("data-auth-root", "");
    controls.insertBefore(root, controls.firstChild);
    return root;
  }

  function renderLoggedOut(root) {
    root.innerHTML =
      '<a class="auth-signin" href="/auth/google">Sign in with Google</a>';
  }

  function renderLoggedIn(root, user) {
    var label = escapeHtml(displayName(user));
    var avatar = user.picture
      ? '<img class="auth-avatar" src="' +
        escapeHtml(user.picture) +
        '" alt="" width="20" height="20" referrerpolicy="no-referrer"/>'
      : "";
    root.innerHTML =
      '<span class="auth-user">' +
      avatar +
      '<span class="auth-login">' +
      label +
      "</span></span>" +
      '<a class="auth-signout" href="/auth/logout?next=' +
      encodeURIComponent(window.location.pathname || "/") +
      '">Sign out</a>';
  }

  function updateCreateCue(user) {
    document.querySelectorAll("[data-auth-cue]").forEach(function (el) {
      if (user && user.logged_in && displayName(user)) {
        el.hidden = false;
        el.textContent =
          "Signed in as " + displayName(user) + " — login is optional.";
      } else {
        el.hidden = true;
        el.textContent = "";
      }
    });
  }

  function mountAuth() {
    var controlsList = document.querySelectorAll(".header-controls");
    if (!controlsList.length) return;

    fetch("/auth/me", { cache: "no-store", credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) throw new Error("auth me failed");
        return res.json();
      })
      .then(function (data) {
        controlsList.forEach(function (controls) {
          var root = ensureAuthRoot(controls);
          if (data && data.logged_in) {
            renderLoggedIn(root, data);
          } else if (data && data.oauth_configured) {
            renderLoggedOut(root);
          } else {
            root.innerHTML = "";
          }
        });
        updateCreateCue(data);
      })
      .catch(function () {
        /* Localhost spectator without Pages auth — stay quiet. */
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAuth);
  } else {
    mountAuth();
  }
})();
