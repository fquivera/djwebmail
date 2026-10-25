# Folder-scoped message search

`GET /mail/search/` returns the same message-list partial used by
`/mail/folder/<folder>/`. The feature is the first Phase 4 deliverable; see
`docs/phase-4.md` for the rest of the scope.

## Request contract

| Parameter | Meaning | IMAP criterion |
|---|---|---|
| `folder` | Folder to search; defaults to `INBOX` | `SELECT` target |
| `q` | Free text over headers and body | `TEXT` |
| `from` | Sender substring | `FROM` |
| `to` | Recipient substring | `TO` |
| `subject` | Subject substring | `SUBJECT` |
| `date_from` | First day to include (`YYYY-MM-DD`) | `SINCE` |
| `date_to` | Last day to include (`YYYY-MM-DD`) | `BEFORE` with one day added |
| `unread` | Only unseen messages | `UNSEEN` |

All supplied criteria are combined with IMAP's implicit AND. An empty request
is equivalent to the folder listing (`ALL`).

`has_attachment` from the upstream contract is deliberately not accepted yet:
standard `UID SEARCH` has no reliable attachment criterion, and guessing with
`HEADER Content-Type` produces false positives and false negatives. It stays
documented as deferred instead of being implemented by analogy.

The validation lives in `apps/mail/forms.py`; the criteria translation lives in
`apps/mail/services/search.py`. Criteria are passed to `imapclient` as a list,
so the client performs quoting and literal handling. The code never
concatenates user input into a raw IMAP command string.

## Response contract

- Without `HX-Request`, the full `mail/index.html` page renders with the bound
  search form and the results.
- With `HX-Request`, only `mail/_message_list.html` is returned for the
  `#message-list-results` target.
- The search form targets `#message-list-results`; folder navigation targets
  `#message-list` and replaces both the form and the results.
- Pagination links use `pagination_url` plus the serialized search filters, so
  `?page=N` never loses `folder`, `q`, or the advanced filters.
- Invalid filters return `200` with an alert and field errors. HTMX does not
  swap 4xx responses by default, so validation failures must stay 2xx.
- `HX-Push-URL` is enabled on the form and pagination links; a full page load of
  the pushed URL produces the same result.

## UTF-8 fallback

IMAP only requires US-ASCII search support. The first attempt uses `CHARSET
UTF-8`. If the server raises `ImapProtocolError`, the service:

1. folds `q`, `from`, `to`, and `subject` to ASCII with `NFKD` normalization;
2. retries with `charset=None` (US-ASCII);
3. returns `used_ascii_fallback=True`, which renders a discreet warning.

The warning is explicit about the approximation; it does not silently pretend
the results are complete. If the fallback also fails, the normal `MailError`
handling renders the mail-unavailable alert.

## Search state and edge cases

- The result count and empty state are shared with the folder list. When filters
  are active, an empty result says "No messages match your search."
- Searching the current folder does not change the selected folder or the
  folder tree.
- Flags and moves keep the existing row-level behavior. A row that no longer
  matches an `unread` filter is not removed until the next request; that is
  consistent with the current list model and is a candidate for the all-folder
  follow-up.
- Global search across all selectable folders is Phase 4 item 2, not part of
  this route.
- The command palette (`/mail/palette/`) reuses this folder-scoped service with
  only `folder` and `q`, and is likewise limited to the current folder. Its
  contract is in [`docs/ui-interaction.md`](ui-interaction.md).

## Tests

- `apps/mail/tests/test_search.py` covers criteria translation, `SINCE`/`BEFORE`
  boundaries, query-string round trips, pagination, and ASCII fallback.
- `apps/mail/tests/test_views.py` covers login protection, full-page and HTMX
  branches, bound form values, `from` as the public parameter name, pagination
  preservation, empty results, fallback notice, and reversed dates.

## Evidence

- `docs/upstream/migracion-django-fase3.md` §6.3 (search parameters, same
  partial, UTF-8 fallback).
- `docs/upstream/migracion-django-fase0-2.md` (IMAP `UID SEARCH`, UTF-8 and
  fallback limitation).
