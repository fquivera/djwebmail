# Message search

`GET /mail/search/` returns the same message-list partial used by
`/mail/folder/<folder>/`. Search runs either inside the selected folder
(default) or across every selectable folder. Phase 4 scope and close-out status
live in `docs/phase-4.md`.

## Request contract

| Parameter | Meaning | IMAP criterion |
|---|---|---|
| `folder` | Folder context; search target in folder scope | `SELECT` target |
| `scope` | `folder` (default) or `all` | one search per selectable folder when `all` |
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
  `?page=N` never loses `scope`, `folder`, `q`, or the advanced filters.
- Invalid filters return `200` with an alert and field errors. HTMX does not
  swap 4xx responses by default, so validation failures must stay 2xx.
- `HX-Push-URL` is enabled on the form and pagination links; a full page load of
  the pushed URL produces the same result.

## Global scope

`scope=all` searches every selectable folder. IMAP has no cross-folder search,
so the service selects each folder, runs the same criteria, and merges the
results locally:

1. `LIST` provides the folder set; `\Noselect` folders are skipped.
2. Each folder is searched with the same validated criteria and its newest
   `GLOBAL_SEARCH_PER_FOLDER_LIMIT` matching UIDs are fetched.
3. Headers are parsed once per message and summary rows keep their source
   folder, so every result row links to the correct message and shows a folder
   badge.
4. Rows are ordered by message date descending, then folder name, then UID.
   That key makes the merged page deterministic across requests.
5. The total and page count are computed from the bounded merged set. When any
   folder was capped, the response renders a notice stating the per-folder
   limit instead of presenting a partial result as complete.

The per-folder cap is a domain constant, not a deployment setting. It bounds the
IMAP work for one request and prevents a large mailbox from monopolizing the
worker. Global pagination is therefore over the newest matches per folder, not
over the unbounded mailbox; this is the documented trade-off.

The folder search form exposes an explicit `This folder` / `All folders`
selector. The command palette is always global: it reuses the same service and
keeps the folder badge on every result. Its "Search all folders" action copies
the palette query into the main search form, selects the global scope, and
submits it.

## UTF-8 fallback

IMAP only requires US-ASCII search support. The first attempt uses `CHARSET
UTF-8`. If the server raises `ImapProtocolError`, the service:

1. folds `q`, `from`, `to`, and `subject` to ASCII with `NFKD` normalization;
2. retries with `charset=None` (US-ASCII);
3. returns `used_ascii_fallback=True`, which renders a discreet warning.

Global scope restarts the scan for all selectable folders with the folded
criteria, so a late failure cannot leave a mix of UTF-8 and ASCII results. The
warning is explicit about the approximation; it does not silently pretend the
results are complete. If the fallback also fails, the normal `MailError`
handling renders the mail-unavailable alert.

## Search state and edge cases

- The result count and empty state are shared with the folder list. When filters
  are active, an empty result says "No messages match your search."
- Searching the current folder does not change the selected folder or the
  folder tree. Global scope keeps the current folder context in the tree while
  the heading reads "All folders".
- Flags and moves keep the existing row-level behavior. A row that no longer
  matches an `unread` filter is not removed until the next request; that is
  consistent with the current list model.
- A global result row links to its own folder and carries `scope=all` into the
  viewer, so read/star out-of-band row updates keep the folder badge.
- The command palette reuses the global service with a short page size; its
  contract is in [`docs/ui-interaction.md`](ui-interaction.md).

## Tests

- `apps/mail/tests/test_search.py` covers criteria translation, `SINCE`/`BEFORE`
  boundaries, query-string round trips, pagination, ASCII fallback, selectable
  folder filtering, date merging, deterministic tie-breaks, and the per-folder
  cap.
- `apps/mail/tests/test_views.py` covers login protection, full-page and HTMX
  branches, bound form values, `from` as the public parameter name, pagination
  preservation, empty results, fallback notice, reversed dates, the global
  scope selector, folder badges, truncation notice, viewer scope propagation,
  and the global command palette.

## Evidence

- `docs/upstream/migracion-django-fase3.md` §6.3 (search parameters, same
  partial, UTF-8 fallback).
- `docs/upstream/migracion-django-fase0-2.md` (IMAP `UID SEARCH`, UTF-8 and
  fallback limitation).
