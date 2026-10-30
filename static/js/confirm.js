/* Native confirmation dialogs without inline script.
 *
 * Any element with data-confirm-open="<dialog-id>" opens the matching
 * <dialog> with showModal(), which gives focus trapping and Escape for free.
 * The dialog closes itself through method="dialog" forms; the destructive
 * action stays a normal POST (or an htmx request) so it works without eval
 * and inside the strict Content-Security-Policy.
 */
(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    if (!(event.target instanceof Element)) {
      return;
    }
    var closeTrigger = event.target.closest("[data-confirm-close]");
    if (closeTrigger) {
      var d = closeTrigger.closest("dialog");
      if (d && typeof d.close === "function") {
        event.preventDefault();
        d.close();
      }
      return;
    }
    var trigger = event.target.closest("[data-confirm-open]");
    if (!trigger) {
      return;
    }
    var dialog = document.getElementById(
      trigger.getAttribute("data-confirm-open"),
    );
    if (dialog && typeof dialog.showModal === "function") {
      event.preventDefault();
      dialog.showModal();
    }
  });
})();
