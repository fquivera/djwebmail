/* Apply theme and density changes without a full page reload.
 *
 * The server remains the source of truth: it stores the preference and renders
 * the initial data-theme/data-density attributes. The save response emits the
 * mail:preference-changed event with the new values, and this listener mirrors
 * them onto <html> for immediate feedback.
 */
(function () {
  "use strict";

  var themeAttributes = {
    light: "mail-light",
    dark: "mail-dark",
  };

  document.addEventListener("mail:preference-changed", function (event) {
    var detail = event.detail || {};

    if (typeof detail.theme === "string") {
      var attribute = themeAttributes[detail.theme];
      if (attribute) {
        document.documentElement.dataset.theme = attribute;
      } else {
        document.documentElement.removeAttribute("data-theme");
      }
    }

    if (typeof detail.density === "string") {
      document.documentElement.dataset.density = detail.density;
    }
  });

  function updateRule(elementId, passed) {
    var el = document.getElementById(elementId);
    if (!el) {
      return;
    }
    var icon = el.querySelector(".status-icon");
    if (passed) {
      el.classList.remove("text-base-content/50");
      el.classList.add("text-success", "font-medium");
      if (icon) {
        icon.textContent = "✓";
      }
    } else {
      el.classList.remove("text-success", "font-medium");
      el.classList.add("text-base-content/50");
      if (icon) {
        icon.textContent = "○";
      }
    }
  }

  function initPasswordMeter() {
    var form = document.getElementById("password-form");
    if (!form) {
      return;
    }

    var newPass = form.querySelector('[data-password-input="new"]');
    var confirmPass = form.querySelector('[data-password-input="confirm"]');
    var strengthBar = document.getElementById("strength-bar");
    var strengthLabel = document.getElementById("strength-label");

    if (!newPass) {
      return;
    }

    function evaluate() {
      var val = newPass.value || "";
      var confirmVal = confirmPass ? confirmPass.value || "" : "";

      var hasLen = val.length >= 12;
      var hasUpper = /[A-Z]/.test(val);
      var hasLower = /[a-z]/.test(val);
      var hasCase = hasUpper && hasLower;
      var hasNum = /[0-9]/.test(val);
      var hasSym = /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]/.test(val);
      var hasMatch = val.length > 0 && val === confirmVal;

      updateRule("rule-length", hasLen);
      updateRule("rule-casing", hasCase);
      updateRule("rule-number", hasNum);
      updateRule("rule-symbol", hasSym);
      updateRule("rule-match", hasMatch);

      if (!strengthBar || !strengthLabel) {
        return;
      }

      if (!val) {
        strengthBar.className = "h-full w-0 transition-all duration-300 bg-base-300";
        strengthLabel.textContent = "—";
        strengthLabel.className = "font-semibold text-base-content/60";
        return;
      }

      var score = 0;
      if (hasLen) score += 2;
      if (hasUpper) score += 1;
      if (hasLower) score += 1;
      if (hasNum) score += 1;
      if (hasSym) score += 1;

      if (score < 3) {
        strengthBar.className = "h-full w-1/4 transition-all duration-300 bg-error";
        strengthLabel.textContent = "Débil";
        strengthLabel.className = "font-semibold text-error";
      } else if (score < 5) {
        strengthBar.className = "h-full w-3/5 transition-all duration-300 bg-warning";
        strengthLabel.textContent = "Media";
        strengthLabel.className = "font-semibold text-warning";
      } else {
        strengthBar.className = "h-full w-full transition-all duration-300 bg-success";
        strengthLabel.textContent = "Fuerte";
        strengthLabel.className = "font-semibold text-success";
      }
    }

    newPass.addEventListener("input", evaluate);
    if (confirmPass) {
      confirmPass.addEventListener("input", evaluate);
    }
    evaluate();
  }

  document.addEventListener("click", function (event) {
    var btn = event.target.closest("[data-password-toggle]");
    if (!btn) {
      return;
    }
    var targetId = btn.getAttribute("data-password-toggle");
    var input = targetId ? document.getElementById(targetId) : null;
    if (input) {
      input.type = input.type === "password" ? "text" : "password";
    }
  });

  function applySection(val) {
    var select = document.getElementById("settings-section-selector");

    if (select && select.value !== val) {
      select.value = val;
    }

    var sections = ["preferences", "password", "filters", "vacation"];
    sections.forEach(function (sec) {
      var el = document.getElementById("section-" + sec);
      if (el) {
        if (sec === val) {
          el.classList.remove("hidden");
        } else {
          el.classList.add("hidden");
        }
      }
    });
  }

  document.addEventListener("change", function (event) {
    var select = event.target.closest("#settings-section-selector");
    if (!select) {
      return;
    }
    applySection(select.value);
    if (window.history && window.history.replaceState) {
      var url = new URL(window.location.href);
      url.searchParams.set("section", select.value);
      window.history.replaceState({}, "", url.toString());
    }
  });

  function initSectionSelector() {
    var select = document.getElementById("settings-section-selector");
    var params = new URLSearchParams(window.location.search);
    var initialSection = params.get("section") || (select ? select.value : "preferences");
    if (initialSection) {
      applySection(initialSection);
    }
  }

  function initAll() {
    try {
      initPasswordMeter();
    } catch (e) {
      // Prevent password meter from breaking section switching
    }
    initSectionSelector();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }

  document.addEventListener("htmx:afterSettle", function (event) {
    if (event.detail && event.detail.target && event.detail.target.id === "password-form") {
      initPasswordMeter();
    }
  });
})();
