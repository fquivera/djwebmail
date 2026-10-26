# Message viewer and HTML sanitization

## Endpoints

- `GET /mail/message/<folder>/<uid>/` renders one message. It returns a full
  page without the `HX-Request` header and an HTMX fragment targeting
  `#message-viewer` with it.
- `POST /mail/message/<folder>/<uid>/remote-images/` re-renders only the body
  with remote images proxied through `/mail/image-proxy/` (HTMX, targets
  `#message-body`).
- `GET /mail/image-proxy/?u=<url>` streams one validated remote image as
  same-origin bytes.
- `GET /mail/message/<folder>/<uid>/attachment/<part>/` streams one MIME part as
  a download.
- `GET /mail/message/<folder>/<uid>/inline/<part>/` streams one inline image
  part referenced by `cid:`.
- `POST /mail/message/<folder>/<uid>/flags/` applies a read/star change
  (`action` = `read` | `unread` | `star` | `unstar`).
- `POST /mail/message/<folder>/<uid>/move/` moves the message to `dest` and
  redirects to that folder.
- `POST /mail/message/<folder>/<uid>/delete/` permanently deletes the message
  and redirects to its folder.

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
blockquotes, code, tables, inline emphasis, and `<img>`. The sanitizer removes:

- `<script>`, `<style>`, `<iframe>`, `<object>`, `<embed>`, media elements;
- event handlers (`onclick`, `onerror`, ...) and `javascript:` URLs;
- `<img>` sources other than `http:`, `https:`, and `cid:`.

`<img>` is kept so inline and remote sources can be rewritten afterwards: `cid:`
to the inline endpoint, and remote HTTP(S) to the image proxy. External links
are rewritten with `rel="noopener noreferrer nofollow"` and `target="_blank"`.

### Why `nh3`

- `nh3` is a maintained Rust binding to the `ammonia` sanitizer; `bleach` is
  deprecated and unmaintained.
- The standard library has no HTML sanitizer; Django's `strip_tags` is
  destructive and is not an HTML sanitizer. Writing a whitelist parser by hand
  is the kind of security code that must not be reinvented.

## Remote-content blocking and the image proxy

The viewer blocks remote content by default: images, iframes, stylesheets, and
`url(...)` backgrounds are stripped and a warning banner tells the user content
was blocked.

The banner offers a "load images" action. It re-fetches the message
(`BODY.PEEK[]`), keeps only plain HTTP(S) `<img>` sources, and rewrites each to
`/mail/image-proxy/?u=<url>`. The CSP allows only `img-src 'self'`, so the proxy
is the sole way a remote image reaches the viewer.

The proxy is an anti-SSRF boundary:

- schemes are limited to `http`/`https`;
- the host is resolved and every address must be globally routable (private,
  loopback, link-local, reserved, multicast, and unspecified are rejected);
- redirects are refused;
- the response content type must be a raster image (`png`, `jpeg`, `gif`,
  `webp`); SVG is rejected because serving it same-origin could run script if
  navigated;
- the response is streamed with a byte limit and a timeout
  (`DJANGO_MAIL_IMAGE_PROXY_MAX_BYTES`,
  `DJANGO_MAIL_IMAGE_PROXY_TIMEOUT_SECONDS`).

DNS rebinding between the validation lookup and the fetch is a known residual
risk; connecting to the pre-validated address is a later hardening step.

## Attachments and inline images

MIME parts that are not the body are exposed as attachments and listed under the
message. Each entry links to `/attachment/<part>/`, which streams the decoded
part bytes with a sanitized `Content-Disposition`.

Inline images referenced by `Content-ID` are not listed as attachments. Their
`cid:` references in the sanitized body are rewritten to `/inline/<part>/`, so
they render inline (they are embedded content, not remote content). The inline
endpoint only serves raster image types (`png`, `jpeg`, `gif`, `webp`), matching
the image proxy's allowlist; anything else returns 404.

Attachments and inline parts are served from a fresh `BODY.PEEK[]` fetch. For
large messages a later change should fetch only the requested part with
`BODY.PEEK[<part>]`.

## Read and star flags, move, and delete

Opening a message marks it read: the viewer fires a `read` flag request on load
(`hx-swap="none"`) and the message-list row is refreshed out-of-band. Read/unread
and star controls in the viewer header use the same endpoint. The response only
replaces the list row (`hx-swap-oob="outerHTML"`); it never replaces the viewer.
That keeps the Alpine optimistic state intact while the server confirms the
change. On a non-2xx response the component reverts and shows an error alert.

The list row carries a stable `id="msg-<uid>"` and `data-unread` so HTMX can
swap it and CSS can style the unread state without duplicating Tailwind
conditionals. The endpoint returns `503` for mail failures, not the normal `200`
error partial, so HTMX does not mistake a failed flag change for success. On the
standalone full-page route the forms send `standalone=1` and the endpoint returns
`204`: there is no list row to refresh, and an OOB row would have no target. See
[`docs/ui-interaction.md`](ui-interaction.md).

A folder `<select>` in the viewer header moves the message to another selectable
folder and redirects there. Flags and move are written with
`ImapService.store_flags` / `ImapService.move` on a read-write selection.

Delete opens a native `<dialog>` confirmation (no `window.confirm`, no
`hx-confirm`) handled by `static/js/confirm.js`, which traps focus and closes on
`Escape` for free. Confirming posts to the delete endpoint, which marks the
message `\Deleted` and expunges it; the response redirects to the folder. The
dialog states that the removal is permanent. A list-level batch delete that
moves selected messages to Trash (the endpoint in
`docs/upstream/migracion-django-fase3.md` §6.5) is deferred until selection
checkboxes exist.

## Tests

- `apps/mail/tests/test_message.py` covers the sanitizer allowlist, link
  hardening, remote-content detection, HTML/plain selection, image rewriting,
  attachment/cid extraction, and empty bodies.
- `apps/mail/tests/test_image_proxy.py` covers scheme/host validation, public-IP
  checks, size and content-type limits, and private-host rejection.
- `apps/mail/tests/test_views.py` covers login enforcement, full page vs HTMX
  fragment, the remote-content warning, the proxied-body action, attachment and
  inline streaming, and IMAP errors.
- `tests/functional/test_mail_stack.py` sends real messages over SMTP and
  asserts the rendered viewer strips scripts/tracking images, blocks remote
  content, and lists + streams an attachment.
