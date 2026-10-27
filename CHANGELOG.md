## 0.2.1 (2026-10-26)

### Fix

- **preferences**: use `gettext_lazy` on `MailPreference.Meta` so non-English `DJANGO_LANGUAGE_CODE` does not report unmigrated model changes

### Docs

- **deployment**: include `127.0.0.1,localhost` in `DJANGO_ALLOWED_HOSTS` for container healthchecks

## 0.2.0 (2026-10-26)

### Feat

- **mail**: add batch selection toolbar, auto-create Sent folder, and localize standard folder labels (#32)
- **mail**: add account signature, remote image policy, and Sent append (#31)
- **ui**: modernize home, login, and settings interfaces (#30)
- **mail**: add row hover quick actions, reply all, and redesign message viewer (#29)
- **compose**: add rich text editor, plain text toggle, and bcc support (#28)
- **mail**: modernize visual layout with 3-pane app shell and icons (#27)
- **mail**: add global message search (#26)
- **mail**: add responsive shell, command palette, and optimistic flags (#25)
- **mail**: add folder-scoped message search (#24)
- **preferences**: add settings UI and accessibility polish (#23)
- **compose**: add attachments and draft autosave (#22)
- **compose**: add compose, reply, forward, and SMTP send (#21)
- **mail**: add delete with confirmation dialog (#20)
- **mail**: add move-to-folder action (#19)
- **mail**: add message flags (mark read and star) (#18)
- **mail**: add message attachments and inline images (#17)

### Docs

- add production deployment guide and update roadmap (#33)

## 0.1.0 (2026-10-23)

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
