# Compose and SMTP send

Scope: compose a new message, reply, forward, and deliver it over SMTP using
the credentials already stored for the IMAP session.

## Routes

- `GET /compose/` renders an empty form.
- `GET /compose/reply/<folder>/<uid>/` prefills `To` with the original sender
  and prefixes the subject with `Re:`.
- `GET /compose/forward/<folder>/<uid>/` prefixes the subject with `Fwd:` and
  quotes the original body as plain text.
- `POST /compose/send/` validates the form and hands the message to SMTP.
- `POST /compose/attachments/` stores uploaded files for the session and
  returns the attachment-list partial.
- `POST /compose/attachments/<id>/delete/` removes one stored attachment.
- `POST /compose/draft/` autosaves the form text and returns HTTP 204.

A successful send redirects to `/mail/`. Validation errors re-render the form
with HTTP 422; SMTP failures use 503.

## Attachments

Attachments are uploaded from the `Attachments` field with an HTMX multipart
`POST`. The server validates each file, stores it in the cache under an opaque
per-session scope, and returns `templates/compose/_attachment_list.html`. The
partial renders one hidden `attachment_ids` input per file inside the compose
form; the final `POST /compose/send/` carries those ids and the service loads
the bytes again to assemble the MIME message.

- Limits: `MAIL_MAX_ATTACHMENT_BYTES` per file, `MAIL_MAX_ATTACHMENTS` files,
  and `MAIL_MAX_ATTACHMENTS_TOTAL_BYTES` in aggregate.
- Lifetimes: `MAIL_COMPOSE_TTL_SECONDS` (default one hour). A successful send
  clears both the attachments and the draft.
- Names pass through `get_valid_filename`; content types are accepted only when
  they match the MIME token grammar, otherwise they are guessed from the name
  or fall back to `application/octet-stream`.
- Attachment bytes live in the cache (Redis in production), never in
  PostgreSQL, the browser session, or the logs.
- Upload errors return the partial with HTTP 200 so HTMX can swap the message;
  this replaces the JSON/413 contract in the phase document.

## Draft autosave

While the new-message form is open, a background HTMX element posts the text
fields (`To`, `Cc`, `Subject`, `Message`) after five seconds without input. The
draft is stored in the cache under the session scope and restored on the next
`GET /compose/`. Empty drafts are deleted rather than stored. Reply and forward
forms do not autosave, so they cannot overwrite a new-message draft.

The draft is deliberately not appended to IMAP yet: each autosave would create
a new message and there is no draft UID tracking. Sent-folder append remains
deferred.

## Service boundaries

- `apps/compose/forms.py` validates recipients, subject, and body. Addresses are
  parsed with `email.utils.getaddresses`, validated one by one, and rejected if
  they contain line breaks. `MAX_RECIPIENTS` lives in
  `apps/compose/constants.py`.
- `apps/compose/services.py` assembles the RFC 5322 message (`From`, `To`, `Cc`,
  `Subject`, `Date`, `Message-ID`), attaches the stored files, and calls
  `SmtpService.send(sender, recipients, raw)`.
- `apps/compose/attachments.py` owns transient attachment storage, limits, and
  filename/content-type sanitization.
- `apps/compose/drafts.py` owns the transient draft text.
- `apps/accounts/services/smtp.py` owns connection setup for `ssl`,
  `starttls`, and `none`, verifies TLS according to `MAIL_VERIFY_TLS`, logs in
  with the account address, and maps `smtplib` failures to
  `SmtpAuthError` / `SmtpConnectionError` / `SmtpSendError`.
- `apps/compose/views.py` only validates input, calls the service, and chooses a
  response.

## Credentials

The SMTP password is the same Fernet-encrypted credential stored for IMAP under
the opaque server-side session key. `get_mail_smtp_service(request)` decrypts it
in memory per request. It never enters the database, the browser, templates, or
logs.

## Security

- CSRF protection through the Django form token.
- Header injection is rejected before assembly: no `\r` or `\n` in recipients or
  subject.
- The body is sent as `text/plain`; no user HTML is rendered or forwarded.
- Recipient count is bounded by `MAX_RECIPIENTS`.
- SMTP failures surface fixed translated messages, never server responses or
  credentials.

## Reply and forward

Reply/forward fetch the message with `get_message` on a read-only IMAP
selection, so prefilling does not mark it read. The forward body is built from
the sanitized body HTML converted to text; attachments are not copied in this
iteration.

## Deferred from `docs/upstream/migracion-django-fase3.md` §6.6

- Upload progress and the JSON/XHR upload contract; HTMX multipart is used
  instead.
- Appending the draft and the sent message to IMAP folders.
- The `#compose-host` panel and `composer.js`; this iteration uses a full page
  so it works without Alpine.
- Recipient autocomplete and the `c` keyboard shortcut.

## Tests

- `apps/accounts/tests/test_smtp.py`: STARTTLS, login, failure mapping, send.
- `apps/compose/tests/test_forms.py`: recipient parsing and injection rejection.
- `apps/compose/tests/test_attachments.py`: storage, limits, sanitization, and
  session isolation.
- `apps/compose/tests/test_drafts.py`: save/load/clear, empty drafts, clamping,
  and session isolation.
- `apps/compose/tests/test_services.py`: message assembly, attachments,
  reply/forward prefill, HTML-to-text.
- `apps/compose/tests/test_views.py`: login gate, validation, delivery, SMTP
  error mapping, reply/forward prefill, IMAP failure, uploads, removal, and
  draft autosave.
- `tests/functional/test_mail_stack.py::test_compose_send_delivers_over_smtp`
  and `::test_compose_attachment_is_delivered_over_smtp`: end-to-end delivery
  through GreenMail and visibility over IMAP.
