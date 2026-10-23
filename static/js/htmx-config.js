/* HTMX hardening for the strict Content-Security-Policy.
 *
 * Loaded after htmx.min.js and before DOMContentLoaded, so every option below
 * is applied before htmx initializes. No eval, no script execution from
 * swapped HTML, and no inline indicator styles (they live in styles.css).
 */
(function () {
  if (typeof window.htmx === "undefined") {
    return;
  }
  window.htmx.config.allowEval = false;
  window.htmx.config.allowScriptTags = false;
  window.htmx.config.includeIndicatorStyles = false;
})();
