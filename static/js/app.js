// Small progressive enhancements. Everything works without JavaScript.
(function () {
  "use strict";

  var ERROR_MESSAGES = {
    400: "That request was not valid.",
    403: "You do not have permission to do that. Try reloading the page.",
    404: "That item no longer exists.",
    429: "You are doing that too often. Please wait a moment.",
    503: "Movie data is temporarily unavailable. Please try again shortly.",
  };

  function dismiss(toast) {
    if (!toast || toast.dataset.leaving) return;
    toast.dataset.leaving = "1";
    toast.classList.add("opacity-0", "translate-y-2");
    setTimeout(function () { toast.remove(); }, 250);
  }

  function initToasts() {
    document.querySelectorAll("[data-toast]:not([data-ready])").forEach(function (toast) {
      toast.dataset.ready = "1";
      setTimeout(function () { dismiss(toast); }, 5000);
    });
  }

  function showToast(message, level) {
    var region = document.getElementById("toasts");
    if (!region) return;
    var tpl = document.getElementById("toast-template");
    if (!tpl) return;
    var node = tpl.content.firstElementChild.cloneNode(true);
    node.querySelector("[data-toast-message]").textContent = message;
    if (level === "error") node.classList.add("ring-ember/40");
    region.appendChild(node);
    initToasts();
  }

  function closeMenus(except) {
    document.querySelectorAll("details[data-menu][open]").forEach(function (menu) {
      if (menu !== except) menu.removeAttribute("open");
    });
  }

  document.addEventListener("click", function (event) {
    var dismissBtn = event.target.closest("[data-toast-dismiss]");
    if (dismissBtn) dismiss(dismissBtn.closest("[data-toast]"));

    var menu = event.target.closest("details[data-menu]");
    closeMenus(menu);

    var navToggle = event.target.closest("[data-nav-toggle]");
    if (navToggle) {
      var panel = document.getElementById(navToggle.getAttribute("aria-controls"));
      var open = navToggle.getAttribute("aria-expanded") === "true";
      navToggle.setAttribute("aria-expanded", String(!open));
      if (panel) panel.hidden = open;
    }

    var scrollBtn = event.target.closest("[data-scroll]");
    if (scrollBtn) {
      var track = document.getElementById(scrollBtn.getAttribute("data-target"));
      if (track) {
        var direction = scrollBtn.getAttribute("data-scroll") === "left" ? -1 : 1;
        track.scrollBy({ left: direction * track.clientWidth * 0.85, behavior: "smooth" });
      }
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeMenus(null);
  });

  // Character counters for textareas with data-counter="<id of output>".
  document.addEventListener("input", function (event) {
    var el = event.target;
    if (!el.matches || !el.matches("textarea[data-counter]")) return;
    var out = document.getElementById(el.getAttribute("data-counter"));
    if (out) out.textContent = el.value.length + " / " + el.getAttribute("maxlength");
  });

  // Global progress bar while any HTMX request is in flight.
  var pending = 0;
  function setProgress(delta) {
    pending = Math.max(0, pending + delta);
    var bar = document.getElementById("global-progress");
    if (bar) bar.classList.toggle("opacity-100", pending > 0);
  }
  document.addEventListener("htmx:beforeRequest", function () { setProgress(1); });
  document.addEventListener("htmx:afterRequest", function () { setProgress(-1); });

  document.addEventListener("DOMContentLoaded", initToasts);
  document.addEventListener("htmx:afterSettle", initToasts);
  document.addEventListener("htmx:oobAfterSwap", initToasts);

  document.addEventListener("htmx:responseError", function (event) {
    var status = event.detail.xhr.status;
    showToast(ERROR_MESSAGES[status] || "Something went wrong. Please try again.", "error");
  });
  document.addEventListener("htmx:sendError", function () {
    showToast("Network error. Check your connection and try again.", "error");
  });
})();
