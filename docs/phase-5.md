# Phase 5 scope: account identity, custom IMAP folders, and jCard contacts

Phase 5 extends DjWebmail with three user-facing capabilities grounded in
SnappyMail evidence and RFC standards:

1. **Account owner identity (`display_name` and `account_label`)** — done
   - Editable in `/settings/` under **Account identity** (`MailPreference`).
   - Mirrored to the server-side session (`mail_display_name`,
     `mail_account_label`) on login and save; updates `#navbar-identity`
     out-of-band via HTMX.
   - Formats outgoing RFC 5322 `From:` headers with `email.utils.formataddr`
     while keeping the bare email address as the SMTP envelope sender.
   - Evidence: `snappymail/v/0.0.0/app/libraries/RainLoop/Model/Identity.php:11-18, 52-55`,
     `dev/Model/Identity.js:10-14, 46-51`, and
     `docs/upstream/migracion-django-fase0-2.md:826-841`.
2. **User-created IMAP folders** — done
   - `POST /mail/folders/create/` (`mail:folder_create`) validates the folder
     name (`FOLDER_NAME_MAX_LENGTH = 64`, no control characters or hierarchy
     delimiter) and creates top-level or nested folders via
     `create_user_folder()` and `ImapService.create_folder()` using the
     server's hierarchy delimiter.
   - Triggered from the `+` (**New folder**) button in the folder sidebar,
     which opens `#create-folder-dialog` with an optional parent-folder
     selector, then redirects (`HX-Redirect` or `302`) to the newly created
     folder.
   - Evidence: `snappymail/v/0.0.0/app/libraries/RainLoop/Actions/Folders.php:114-133`.
3. **Contacts module with jCard (RFC 7095)** — planned (Stage 3)
   - Per-account address book in `apps/contacts/` backed by a canonical RFC 7095
     `jcard` (`["vcard", [...]]`) JSON representation, HTMX search/CRUD,
     `.json` (jCard) import/export, compose recipient autocomplete, and
     one-click contact creation from the message viewer.
   - Evidence: `dev/DAV/JCard.js:1-227`,
     `snappymail/v/0.0.0/app/libraries/RainLoop/Providers/AddressBook/Classes/Contact.php:7-91`.
