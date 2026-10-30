## v0.5.2 (2026-10-29)

### Fix

- **mailadmin**: serve media files in production

## v0.5.1 (2026-10-29)

### Fix

- **mail**: handle tuple id_data in detect_imap_engine

## v0.5.0 (2026-10-29)

### Feat

- **mail**: add Carbonio-style Sieve filters UI in settings and modal builder (#57)
- **mail**: add Sieve RFC 5228 engine, ManageSieve client and database fallback (#56)
- **mail**: add visual and audio notifications for new incoming emails (#55)
- **mailadmin**: add diagnostics dashboard and service health probes (#54)
- **mailadmin**: add mail accounts and storage quotas management (#53)
- **mailadmin**: add corporate identity branding and admin security (#52)
- **common**: make header and footer sticky with responsive mobile layout (#51)
- **common**: add global footer and about modal with imap engine detection (#49)

### Fix

- **i18n**: recompile spanish mo catalog without mojibake and add guard test (#50)

## v0.4.2 (2026-10-28)

### Feat

- **mail**: implement 2-stage message deletion with Trash folder lifecycle (#47)
- **compose**: optimize compose view and formatting toolbar for mobile viewports (#46)
- **mail**: improve responsive layout and navigation for mobile and tablet (#45)

## v0.4.1 (2026-10-27)

### Fix

- **mail**: preserve image dimensions and constrain message body images (#43)

## v0.4.0 (2026-10-27)

### Feat

- **accounts**: add password management and security recommendations (#41)
- **mail**: add blocking modal attachment viewer (#40)
- **mail**: add single, batch, and shortcut message archiving (#39)
- **contacts**: add RFC 7095 jCard contacts module and compose autocomplete (#38)
- **mail**: add user-created IMAP folders and nested subfolders (#37)
- **preferences**: add owner display name and account label identity (#36)

## v0.2.1 (2026-10-26)

### Fix

- **preferences**: use gettext_lazy for model Meta verbose names

## v0.2.0 (2026-10-26)

### Feat

- **mail**: add batch selection toolbar and auto-create Sent folder (#32)
- **mail**: add account signature, remote image policy, and Sent append (#31)
- **ui**: modernize home, login, and settings interfaces (#30)
- **mail**: add row hover quick actions and redesign message viewer (#29)
- **compose**: add rich text editor, plain text toggle, and bcc support (#28)
- **mail**: modernize visual layout with 3-pane app shell and icons (#27)
- **mail**: add global message search (#26)
- **mail**: add responsive shell, palette, and optimistic flags (#25)
- **mail**: add folder-scoped message search (#24)
- **preferences**: add settings UI and accessibility polish (#23)
- **compose**: add attachments and draft autosave (#22)
- **compose**: add compose, reply, forward, and SMTP send (#21)
- **mail**: add delete with confirmation dialog (#20)
- **mail**: add move-to-folder action (#19)
- **mail**: add message flags (mark read and star) (#18)
- **mail**: add message attachments and inline images (#17)

## v0.1.0 (2026-10-23)

### Feat

- **mail**: add anti-SSRF image proxy and load-images action (#15)
- **security**: enforce strict CSP and harden HTMX (#14)
- **mail**: add sanitized message viewer with remote-content blocking (#13)
- **mail**: add folder tree and HTMX message list (#11)
- **dev**: add local mail stack and functional tests (#9)
- **accounts**: add IMAP login and server-side session (#8)
- **preferences**: add per-account mail preferences (#7)
- **accounts**: add request-scoped IMAP service (#6)
- **config**: scaffold Django project with split settings (#4)

### Fix

- **security**: keep same-origin referrer for CSRF (#10)
