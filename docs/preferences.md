# Preferences and accessibility

Scope: one authenticated account can change the presentation choices that the
server can already apply. Mail content and credentials stay in IMAP and in the
encrypted session store; PostgreSQL only holds the preference row.

## Route

- `GET /settings/` renders the full page.
- `POST /settings/` saves the presentation preferences form (`#settings-form`).
- `POST /settings/password/` validates and changes the email password (`#password-form`).
- HTMX requests target `#settings-form` or `#password-form` respectively and swap
  the refreshed fragments in place.
- The routes are `preferences:index` and `preferences:password`; the header exposes
  them only when a mail session exists.

The view is `never_cache`, varies on `HX-Request`, and requires a mail login.
A missing preference row is created on demand for the authenticated account.

## Editable fields

The form exposes only choices that the current application applies:

| Field | Effect |
|---|---|
| `display_name` | Owner display name formatted into outgoing `From: "Name" <email>` headers and shown in the top navigation bar. |
| `account_label` | Optional descriptive tag (e.g., `Work`, `Admin`) shown as a badge in the navigation bar, settings header, and compose header. |
| `language` | Stored in the session and activated with Django translation. |
| `timezone` | Activated per request; message dates use it. |
| `theme` | `light`, `dark`, or `system`; mapped to the daisyUI themes. |
| `density` | `compact` or `comfortable`; controls the message-row height. |
| `page_size` | Page size for the folder message list, bounded by settings. |
| `remote_images` | `ask`, `always`, or `never`; controls whether remote images load through `/mail/image-proxy/` automatically or on demand. |
| `signature_html` | Account signature prefilled in compose, reply, and forward forms. |

`layout`, `use_threads`, and `html_allowed` remain in the model but are
deliberately not exposed yet: their runtime behavior is not implemented, so
showing them would be misleading.

## Precedence and persistence

1. The `MailPreference` row in PostgreSQL is the source of truth.
2. Login copies the values into the server-side session (`mail_theme`,
   `mail_density`, `mail_timezone`, `mail_page_size`).
3. Rendering reads the session, so ordinary mail requests do not need an extra
   database query.
4. Saving the form updates both the row and the session.

There is no `localStorage` preference and no client-side source of truth.

## Security and password change

The `/settings/` page provides a dedicated self-service password update form
(`templates/preferences/_password_form.html`) when `MAIL_CHANGE_PASSWORD_ENABLED`
is true (default: `True`):

- **OWASP ASVS & NIST requirements enforced**:
  - Minimum 12 characters.
  - At least one uppercase letter (`A-Z`).
  - At least one lowercase letter (`a-z`).
  - At least one number (`0-9`).
  - At least one special symbol (`!@#$%^&*()_+-=[]{}|;:,.<>?/~`).
  - Cannot match the current password.
  - Cannot contain the user's email address or username.
  - Rejects repetitive character patterns (e.g. `aaaa`).
- **Real-time UX feedback**:
  - Live interactive checklist updating checkmarks (`✓`) dynamically as the user
    types.
  - Password strength progress bar (`Débil` / `Media` / `Fuerte`).
  - Show/hide password visibility toggles (`data-password-toggle`).
  - Security recommendations banner emphasizing unique passphrases, no password
    reuse across services, and dedicated password managers.
- **Backend drivers**:
  - `DJANGO_MAIL_ACCOUNTS_FILE`: atomic updates to `{SHA512-CRYPT}` hashes in
    Dovecot/docker-mailserver accounts files (`postfix-accounts.cf`).
  - `DJANGO_MAIL_POPPASSD_HOST` / `DJANGO_MAIL_POPPASSD_PORT`: authenticated
    `POPPASSD` protocol communication (port 106).
  - Session rotation: when the backend update succeeds, the session key cycles
    (`request.session.cycle_key()`) and stores the new Fernet-encrypted password,
    keeping the user authenticated smoothly.

## Theme and density

`templates/base.html` maps the session values to the document attributes:

```text
light  -> data-theme="mail-light"
dark   -> data-theme="mail-dark"
system -> no data-theme (daisyUI prefersdark follows the OS)
```

Density is always written as `data-density`; `theme/static_src/src/styles.css`
uses it for `.mail-row` padding.

After an HTMX save the view returns:

```text
HX-Trigger: {"mail:preference-changed": {"theme": "...", "density": "..."}}
```

`static/js/preferences.js` listens for that event and updates the same
attributes immediately. A normal (non-HTMX) save redirects, so the next render
already has the new values. A language change returns `HX-Refresh: true` so the
whole document is translated instead of only the form fragment.

## Page size and time zone

`get_mail_page_size(request)` reads the session and clamps the value to
`MAIL_MAX_PAGE_SIZE`, falling back to `MAIL_DEFAULT_PAGE_SIZE`.
`MailSessionMiddleware` activates `mail_timezone` after Django's locale
middleware. It deactivates the time zone when the session has no valid value,
falling back to `TIME_ZONE`.

## Accessibility

- Skip link as the first body element; it targets `#main-content`, which is a
  focusable `<main>` landmark.
- Header, navigation, main, and the mail sections keep explicit landmark
  roles/labels.
- Django messages render in live regions (`role="status"` or `role="alert"`).
- The message list adds hidden "Unread" text; it never relies on color alone.
- The flag button exposes `aria-pressed`; the settings form uses fieldsets,
  real labels, help text linked with `aria-describedby`, and alert regions for
  errors.
- Focus styles come from the compiled Tailwind/daisyUI CSS; no inline styles
  and no inline scripts are introduced.

## Translations

The Spanish catalog is `locale/es/LC_MESSAGES/django.po`. Its compiled
`django.mo` is committed because the runtime image does not install GNU
gettext; update both files in the same change. Changing the language requires a
full document render so every label, validation message, and template string
uses the new catalog; the HTMX response sends `HX-Refresh` for that reason.

## Tests

- `apps/preferences/tests/test_forms.py`: choices, range validation, save.
- `apps/preferences/tests/test_views.py`: login gate, full page versus partial,
  HTMX trigger/refresh, session updates, invalid responses, theme/density
  attributes, skip link, and Settings visibility.
- `apps/accounts/tests/test_login.py`: login initializes the new session keys.
- `apps/mail/tests/test_views.py`: the message list uses the session page size.
