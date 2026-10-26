# Phase 4 scope: search and keyboard navigation

Phase 3 closed with the viewer, compose, preferences, CSP, and accessibility
work merged. Phase 4 completes the remaining navigation contracts that are
already specified in the SnappyMail evidence, without opening new protocol
areas.

## Deliverables

1. **Folder-scoped search** — done
   - `/mail/search/` with `folder`, `q`, `from`, `to`, `subject`, `date_from`,
     `date_to`, and `unread`.
   - Same message-list partial as the folder listing, with pagination that keeps
     the query string.
   - Debounced HTMX form plus a real GET fallback.
   - ASCII retry and a visible notice when the IMAP server rejects `CHARSET
     UTF-8`.
   - See `docs/mail-search.md`.
2. **Search across all selectable folders** — pending
   - Reuse the folder-scoped service, query each selectable folder, merge by
     date, and show the folder on every row.
   - Requires a bounded per-folder query and a deterministic total/page model.
3. **Keyboard shortcuts** — done
   - `c`, `/`, `j`/`k`, `Enter`, `r`, `e`, `m`, `u`, `?`, and `Escape` as
     specified in `docs/upstream/migracion-django-fase3.md` §8.4, plus the
     user-approved read and move additions.
   - Context guards for inputs, textareas, selects, and `contenteditable`; no
     normal shortcut fires with Ctrl, Meta, or Alt held. Ctrl/Cmd+K owns the
     command palette.
   - See `docs/ui-interaction.md`.
4. **Interaction layer** — done
   - Responsive `?view=list|message` panel selection, mobile folder drawer, and
     native `<dialog>` palette and shortcut help.
   - Alpine CSP build for local state only; HTMX remains the only network path.
   - Optimistic read/star with revert and a visible alert on failure.
   - See `docs/ui-interaction.md` and `docs/security-csp.md`.
5. **Close-out**
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
- `docs/upstream/migracion-django-fase3.md` §4.4 defines the responsive panels.
- `docs/upstream/migracion-django-fase3.md` §8.4 defines the keyboard map.
- The upstream documents are evidence only; implementation decisions are
  recorded here, in `docs/mail-search.md`, and in `docs/ui-interaction.md`.
