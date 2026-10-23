# Strict Content-Security-Policy

The webmail serves a strict CSP that forbids `unsafe-eval` and `unsafe-inline`,
loads no third-party origins, and cannot be framed. It is enforced by
[`django-csp`](https://django-csp.readthedocs.io/) 4.x.

## Policy

Defined once in `config/settings/base.py`:

```python
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "base-uri": ["'self'"],
        "object-src": ["'none'"],
        "frame-ancestors": ["'none'"],
        "form-action": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'"],
        "img-src": ["'self'", "data:", "blob:"],
        "font-src": ["'self'"],
        "connect-src": ["'self'"],
        "media-src": ["'self'"],
    },
    "EXCLUDE_URL_PREFIXES": ("/admin/", "/__debug__/"),
}
```

`CSPMiddleware` runs immediately after `SecurityMiddleware`, so error responses
are covered too.

Consequences of the policy:

- No `unsafe-eval`: HTMX runs with `allowEval=false`; Alpine (when added) is the
  CSP build. `hx-on`, HTMX trigger filters, and `hx-vals="js:"` are forbidden.
- No `unsafe-inline` in styles: no `style="..."` in templates. HTMX's inline
  indicator `<style>` is disabled (`includeIndicatorStyles=false`); the
  indicator styles live in `theme/static_src/src/styles.css`.
- No remote images: `img-src` does not allow `https:`. The viewer blocks remote
  content by default and loads it, on request, through the same-origin
  `/mail/image-proxy/` (see `docs/message-viewer.md`).
- No framing: `frame-ancestors 'none'` plus `X-Frame-Options: DENY`.

## HTMX hardening

`static/js/htmx-config.js` is loaded after `htmx.min.js` and before
`DOMContentLoaded` on the mail page:

```js
window.htmx.config.allowEval = false;
window.htmx.config.allowScriptTags = false;
window.htmx.config.includeIndicatorStyles = false;
```

`allowScriptTags=false` is as important as `allowEval=false`: it stops HTMX from
executing any `<script>` it finds in swapped HTML.

## Admin and debug toolbar

Django admin injects inline scripts and styles, so it is excluded from the
webmail policy via `EXCLUDE_URL_PREFIXES`. It keeps `X-Frame-Options: DENY`.
The Django debug toolbar (`/__debug__/`) is excluded for the same reason in
development.

## Tests

`tests/test_csp.py` asserts the strict header on a webmail page, that `admin`
is excluded, and that the clickjacking/sniffing headers are present.
`tests/test_templates.py` fails on inline `style=`, `hx-on`, `hx-vals="js:"`,
HTMX trigger filters, and inline `<script>` elements without `src`.
