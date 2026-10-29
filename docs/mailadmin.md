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
- **Visual Assets**: `logo_light_url`, `logo_dark_url`, `favicon_url`.

### Integration Across Views
- Exposed globally to templates via `common.context_processors.system_info` under `corporate_identity` and `is_mail_admin`.
- Header: Displays `organization_name` next to the DjWebmail brand.
- Admin button: Rendered conditionally for administrators in the top navigation bar.
- Footer: Kept strictly exclusive to the DjWebmail project copyright.
