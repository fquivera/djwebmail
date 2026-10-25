# Phase 4 scope: search and keyboard navigation

Phase 3 closed with the viewer, compose, preferences, CSP, and accessibility
work merged. Phase 4 completes the remaining navigation contracts that are
already specified in the SnappyMail evidence, without opening new protocol
areas.

## Deliverables

1. **Folder-scoped search** (this change)
   - `/mail/search/` with `folder`, `q`, `from`, `to`, `subject`, `date_from`,
     `date_to`, and `unread`.
   - Same message-list partial as the folder listing, with pagination that keeps
     the query string.
   - Debounced HTMX form plus a real GET fallback.
   - ASCII retry and a visible notice when the IMAP server rejects `CHARSET
     UTF-8`.
2. **Search across all selectable folders**
   - Reuse the folder-scoped service, query each selectable folder, merge by
     date, and show the folder on every row.
   - Requires a bounded per-folder query and a deterministic total/page model.
3. **Keyboard shortcuts**
   - `c`, `/`, `j`/`k`, `Enter`, `r`, `u`, `?`, and `Escape` as specified in
     `docs/upstream/migracion-django-fase3.md` §8.4.
   - Context guards for inputs, textareas, and `contenteditable`; no shortcut
     fires with Ctrl, Meta, or Alt held.
4. **Close-out**
   - Regression tests for both response branches, pagination, fallback, and
     no-JavaScript behavior.
   - Update this document and the affected skill when the contracts change.

## Non-goals

- WYSIWYG compose: the Phase 3 decision is still open; this phase keeps the
  sanitized server-rendered model.
- Sent append, the compose panel, PGP/S/MIME, CardDAV, Sieve, OAuth2, offline
  mode, and a native mobile application.
- Full-text indexing outside IMAP; IMAP remains the source of truth.

## Evidence

- `docs/upstream/migracion-django-fase3.md` §6.3 defines the search parameters
  and the same-partial rule.
- `docs/upstream/migracion-django-fase3.md` §8.4 defines the keyboard map.
- The upstream documents are evidence only; implementation decisions are
  recorded here and in `docs/mail-search.md`.
