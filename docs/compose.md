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

A successful send redirects to `/mail/`. Validation errors re-render the form
with HTTP 422; SMTP failures use 503.

## Service boundaries

- `apps/compose/forms.py` validates recipients, subject, and body. Addresses are
  parsed with `email.utils.getaddresses`, validated one by one, and rejected if
  they contain line breaks. `MAX_RECIPIENTS` lives in
  `apps/compose/constants.py`.
- `apps/compose/services.py` assembles the RFC 5322 message (`From`, `To`, `Cc`,
  `Subject`, `Date`, `Message-ID`) and calls
  `SmtpService.send(sender, recipients, raw)`.
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

- Attachments upload with progress and session/Redis storage.
- Draft autosave and draft restore.
- Appending the sent message to the Sent folder over IMAP.
- The `#compose-host` panel and `composer.js`; this iteration uses a full page
  so it works without Alpine.
- Recipient autocomplete and the `c` keyboard shortcut.

## Tests

- `apps/accounts/tests/test_smtp.py`: STARTTLS, login, failure mapping, send.
- `apps/compose/tests/test_forms.py`: recipient parsing and injection rejection.
- `apps/compose/tests/test_services.py`: message assembly, reply/forward prefill,
  HTML-to-text.
- `apps/compose/tests/test_views.py`: login gate, validation, delivery, SMTP
  error mapping, reply/forward prefill, IMAP failure.
- `tests/functional/test_mail_stack.py::test_compose_send_delivers_over_smtp`:
  end-to-end delivery through GreenMail and visibility over IMAP.
