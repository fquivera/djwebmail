# Mail Server Administration & Corporate Identity

DjWebmail provides a dedicated administrative environment (`/mailadmin/`) to manage the deployment, corporate identity, branding, and server diagnostics.

## 1. Access Control & Security

Access to the `/mailadmin/` environment is restricted by `apps.mailadmin.security.is_mail_admin`, enforcing a defense-in-depth model:

1. **Django Internal Staff / Superusers**: Authenticated Django internal administrators (`user.is_authenticated and (user.is_staff or user.is_superuser)`).
2. **Mail Administrator Accounts**: Webmail users whose email is listed in `DJANGO_MAIL_ADMIN_ACCOUNTS` (configured in settings as `MAIL_ADMIN_ACCOUNTS`).

If an authenticated user lacks administrative privileges, a `403 PermissionDenied` HTTP response is raised. Unauthenticated visitors are redirected to the login view (`/login/?next=...`).

### Settings & Environment Variables

- `DJANGO_MAIL_ADMIN_ACCOUNTS`: Comma-separated list of email addresses granted webmail administration rights (e.g. `admin@example.com,postmaster@example.com`).

## 2. Corporate Identity & Branding

Corporate branding is represented by the `CorporateIdentity` singleton model (`apps/mailadmin/models.py`).

### Fields Configured
- **Organization & Identification**: `organization_name`, `tagline`, `tax_id` (RIF / CIF / NIF / Tax ID).
- **Fiscal Address & Contacts**: `fiscal_address`, `support_email`, `support_phone`.
- **Institutional Links**: `website_url`, `terms_url`, `privacy_url`.
- **Visual Assets**: `logo_light_file` / `logo_light_url`, `logo_dark_file` / `logo_dark_url`, `favicon_file` / `favicon_url`. Each asset supports either a direct image file upload or an external URL (enforced mutually exclusive). Convenience properties `effective_logo_light_url`, `effective_logo_dark_url`, and `effective_favicon_url` resolve the active asset.

### Integration Across Views
- Exposed globally to templates via `common.context_processors.system_info` under `corporate_identity` and `is_mail_admin`.
- Header: Displays `organization_name` next to the DjWebmail brand.
- Admin button: Rendered conditionally for administrators in the top navigation bar.
- Footer: Kept strictly exclusive to the DjWebmail project copyright.

## 3. Mail Accounts & Storage Quotas

Mailbox provisioning and quota limits are managed through the `/mailadmin/accounts/` interface, backed by interchangeable drivers (`apps.mailadmin.drivers`):

### Supported Storage Drivers

1. **Database Driver (`DatabaseMailAccountDriver`)**:
   - Stores mailboxes in the `ManagedMailbox` model.
   - Computes `{SHA512-CRYPT}` password hashes matching Dovecot / Linux crypt standards.
   - Ideal for standalone or containerized deployments managing accounts in PostgreSQL or SQLite.

2. **File Driver (`FileMailAccountDriver`)**:
   - Manages accounts directly in `postfix-accounts.cf` and `dovecot-quotas.cf` (compatible with `docker-mailserver` and standard Dovecot setups).
   - Supports atomic writes using `NamedTemporaryFile` + `os.replace`.
   - Handles account suspension by commenting entries (`#user@domain.com|{SHA512-CRYPT}...`).

### Configuration

- `DJANGO_MAIL_ADMIN_DRIVER`: Driver mode: `"auto"` (default), `"database"`, or `"file"`.
  - In `"auto"` mode, uses `FileMailAccountDriver` if `DJANGO_MAIL_ACCOUNTS_FILE` is set and the file exists; otherwise defaults to `DatabaseMailAccountDriver`.
- `DJANGO_MAIL_ACCOUNTS_FILE`: Absolute path to `postfix-accounts.cf`.

### Features & Capabilities

- **Account Listing & Search**: Real-time search by email or domain with live HTMX filtering.
- **Quota Management**: Storage limits configurable in MB, GB, or Unlimited, formatted cleanly across all views.
- **Password Policies**: Enforces OWASP/NIST minimum complexity rules (length, uppercase, lowercase, numbers, symbols, no username).
- **Status Lifecycle**: Suspend, activate, or permanently delete mailboxes with native modal confirmation.

## 4. Diagnostics & Service Health

The diagnostics dashboard (`/mailadmin/diagnostics/`) provides automated latency probing and runtime verification for mail infrastructure:

### Diagnostic Capabilities

1. **IMAP Connectivity & Latency**:
   - Opens a TCP/SSL socket connection to `DJANGO_MAIL_IMAP_HOST:DJANGO_MAIL_IMAP_PORT`.
   - Reads the greeting banner, identifies the server daemon (Dovecot, GreenMail, Courier, etc.), and parses advertised capabilities (`IMAP4rev1`, `QUOTA`, `IDLE`, `MOVE`, `STARTTLS`).
   - Measures exact round-trip network latency in milliseconds.

2. **SMTP Submission Probe**:
   - Tests connectivity to `DJANGO_MAIL_SMTP_HOST:DJANGO_MAIL_SMTP_PORT`.
   - Sends `EHLO` handshake and discovers active extensions (`STARTTLS`, `AUTH`, `SIZE`, `8BITMIME`).
   - Measures round-trip latency.

3. **Core Services & Database**:
   - Evaluates PostgreSQL / SQLite query latency with a ping query (`SELECT 1`).
   - Validates Redis / cache backend read and write functionality.

4. **Runtime Security & Environment**:
   - Reports Python, Django, and DjWebmail versions.
   - Audits cookie security flags (`HttpOnly`, `Secure`, `CSRF_COOKIE_SECURE`).
   - Checks Fernet encryption availability and DEBUG mode status.


