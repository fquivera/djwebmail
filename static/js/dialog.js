/* Global dialog opener for [data-dialog-open] triggers.
 *
 * Provides native modal support across all templates without inline scripts,
 * complying with strict Content Security Policy (no unsafe-inline).
 */
(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    if (!(event.target instanceof Element)) {
      return;
    }
    var trigger = event.target.closest("[data-dialog-open]");
    if (!trigger) {
      return;
    }
    var targetId = trigger.getAttribute("data-dialog-open");
    if (!targetId) {
      return;
    }
    var dialog = document.getElementById(targetId);
    if (dialog && typeof dialog.showModal === "function" && !dialog.open) {
      if (!trigger.hasAttribute("hx-get") && !trigger.hasAttribute("hx-post")) {
        event.preventDefault();
      }
      dialog.showModal();
    }
  });
})();
