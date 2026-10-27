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

## Upstream Evidence

- `snappymail/v/0.0.0/app/libraries/MailSo/Imap/Enumerations/FolderType.php:15`
  and `dev/Model/Folder.js:11-28`: RFC 6154 `\Archive` special-use attribute and
  `Archive` folder mapping.
- `dev/View/User/MailBox/MessageList.js`: single and batch archive actions move
  messages to the configured Archive folder while keeping the current folder
  context active.
