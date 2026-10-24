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
})();
