# Message viewer and HTML sanitization

## Endpoint

`GET /mail/message/<folder>/<uid>/` renders one message. It returns a full page
without the `HX-Request` header and an HTMX fragment targeting `#message-viewer`
with it.

The view opens the folder read-only and fetches the message with `BODY.PEEK[]`
(`peek=True`), so merely reading a message never sets the `\Seen` flag. Flag
handling is a separate concern.

## Body selection

The parser prefers `text/html`, falls back to `text/plain`, and renders an
empty state when the message has neither (for example an attachment-only
message).

## Sanitization

HTML is sanitized server-side with [`nh3`](https://github.com/messense/nh3)
and only the result is rendered with `|safe` in the template. Nothing is
sanitized in the browser.

Allowed tags are a small structural set: headings, paragraphs, lists,
blockquotes, code, tables, and inline emphasis. The sanitizer removes:

- `<script>`, `<style>`, `<iframe>`, `<object>`, `<embed>`, media elements;
- event handlers (`onclick`, `onerror`, ...) and `javascript:` URLs;
- `<img>` and any embedded or remote resource.

External links are rewritten with `rel="noopener noreferrer nofollow"` and
`target="_blank"`.

### Why `nh3`

- `nh3` is a maintained Rust binding to the `ammonia` sanitizer; `bleach` is
  deprecated and unmaintained.
- The standard library has no HTML sanitizer; Django's `strip_tags` is
  destructive and is not an HTML sanitizer. Writing a whitelist parser by hand
  is the kind of security code that must not be reinvented.

## Remote-content blocking

The viewer blocks remote content by default: images, iframes, stylesheets, and
`url(...)` backgrounds are stripped and a warning banner tells the user content
was blocked. A later change can add an image proxy (`/mail/image-proxy/?u=...`)
and a "load remote images" action that re-renders the body with proxied URLs.

## Tests

- `apps/mail/tests/test_message.py` covers the sanitizer allowlist, link
  hardening, remote-content detection, HTML/plain selection, and empty bodies.
- `apps/mail/tests/test_views.py` covers login enforcement, full page vs HTMX
  fragment, the remote-content warning, and IMAP errors.
- `tests/functional/test_mail_stack.py` sends a real HTML message with a script
  and a tracking image and asserts both are gone from the rendered viewer.
