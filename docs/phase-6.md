# Phase 6 — Archive, Attachment Viewer Modal, and Password Management

Phase 6 adds three core capabilities to DjWebmail:

1. **Professional Email Archiving (`apps/mail/`)**:
   - Single-click and batch archiving into the account's RFC 6154 `\Archive` /
     `Archive` folder (created on demand via `ImapService.create_folder` when
     absent).
   - Available in the message viewer toolbar (`POST /mail/message/<folder>/<uid>/archive/`),
     message row hover quick actions, batch selection bar
     (`POST /mail/folder/<folder>/batch/` with `action="archive"`), and keyboard
     shortcut `y` / `a`.
   - Automatically hidden when browsing the archive folder itself.
2. **Blocking Attachment Viewer Modal (`apps/mail/`)**:
   - Each message attachment includes a **View** (`Visualizar`) button alongside
     **Download** (`Descargar`).
   - Opens `<dialog id="attachment-viewer-dialog" data-modal-strict>` with
     `.showModal()`, blocking all background interaction (`inert` Top Layer,
     no backdrop click-outside dismissal, and `cancel`/`Escape` intercepted in
     `static/js/app.js` until the user clicks **Close**).
   - Supports live inline previews for raster images, PDFs (`X-Frame-Options:
     SAMEORIGIN`, `frame-ancestors 'self'`), UTF-8 text/CSV/Markdown/JSON
     (escaped `<pre>` capped at 256 KB), and audio/video (paused on close),
     while rejecting `image/svg+xml` and `text/html` on the inline endpoint.

## Upstream Evidence

- `snappymail/v/0.0.0/app/libraries/MailSo/Imap/Enumerations/FolderType.php:15`
  and `dev/Model/Folder.js:11-28`: RFC 6154 `\Archive` special-use attribute and
  `Archive` folder mapping.
- `dev/View/User/MailBox/MessageList.js`: single and batch archive actions move
  messages to the configured Archive folder while keeping the current folder
  context active.
- `snappymail/v/0.0.0/app/libraries/RainLoop/Actions/Messages.php` and
  `dev/Model/Attachment.js`: inline vs download attachment disposition and
  preview classification.
