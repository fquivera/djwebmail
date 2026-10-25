# Mail interaction layer

This document defines the client-side contracts that sit on top of the
server-rendered mail shell: responsive panel selection, the command palette,
keyboard shortcuts, and optimistic read/star feedback.

The server remains the source of truth. HTMX performs every mutation and
returns HTML. Alpine holds only local UI state and is loaded from the vendored
CSP build; it never calls the network directly.

## Responsive mail shell

- Desktop (`>= lg`) shows the folder tree, the message list, and the viewer at
  the same time.
- Below `lg`, the shell shows one panel. `/mail/` defaults to `view=list`;
  message links add `?view=message`, and a message deep link renders the message
  panel.
- `static/js/app.js` mirrors the pushed URL into `data-view` after HTMX
  navigation and history restore. The CSS panel switch uses that attribute.
- Folder navigation targets `#message-list` and pushes `?view=list`. The
  response replaces `#folder-heading` out-of-band so the title stays current;
  after a drawer selection, focus moves to the refreshed heading instead of
  staying on a hidden link.
- The folder tree becomes an off-canvas drawer below `lg`. The same
  `mail/_folder_nav.html` partial is used on desktop and in the drawer; it is
  never duplicated.
- Without JavaScript the panels stack vertically and the folder tree stays
  visible. `data-js="true"` is set by `static/js/app.js` before the drawer
  hides panels, so the no-JS fallback remains usable.

## Keyboard shortcuts

The listener is in `static/js/app.js` and is disabled while focus is inside an
input, textarea, select, or `contenteditable` element, or while a modal dialog
is open. Normal shortcuts never fire with Ctrl, Meta, or Alt held; the command
palette uses Ctrl/Cmd+K.

| Key | Action |
|---|---|
| `Ctrl`/`Cmd` + `K` | Open the command palette |
| `c` | Compose |
| `/` | Focus the folder search field (switches to the list first) |
| `j` / `k` | Focus the next / previous message row (switches to the list) |
| `Enter` | Open the focused row (native link behavior) |
| `r` | Reply to the open message |
| `e` | Toggle read/unread for the open message |
| `m` | Focus the move-to-folder selector |
| `u` | Back to the message list |
| `?` | Open the shortcuts dialog |
| `Esc` | Close the native dialog or the mobile folder drawer |

After a message opened from the keyboard or the command palette,
`#message-subject` receives focus so screen readers announce the new view. A
plain mouse click in the list does not steal focus.

## Command palette

`GET /mail/palette/?folder=<folder>&q=<text>` returns a self-contained HTML
fragment for `#palette-results`.

- An empty query returns a hint and does not contact IMAP.
- A non-empty query reuses `search_messages` with `SearchFilters(folder, q)`.
  Results are limited to the current folder by `PALETTE_MESSAGE_LIMIT`; global
  search across every folder remains Phase 4 work.
- Selectable folder names that contain the query are listed separately and
  limited by `PALETTE_FOLDER_LIMIT`.
- Message links target `#message-viewer` and push `?view=message`; folder links
  target `#message-list` and push `?view=list`.
- The form reads the current folder from the search form with `hx-include`, so a
  palette opened after folder navigation searches the new folder.
- Choosing "Search this folder" closes the palette, switches the mobile shell to
  the list, and focuses the search field.
- Invalid filters return `200` with the same alert convention as the search
  form, so HTMX swaps the error instead of silently ignoring a 4xx.
- The palette is available in the `/mail/` shell. The full-page message route
  keeps the shortcuts dialog but not the palette, because its navigation target
  (`#message-viewer`) only exists in the shell.

## Optimistic read and star

The viewer starts Alpine with `data-seen` and `data-flagged` from the server.
The two header controls are HTMX forms with a hidden `action` field:

1. The button changes the local state immediately and updates the hidden action
   (`read`/`unread`, `star`/`unstar`).
2. HTMX posts the form and the endpoint returns only the refreshed list row with
   `hx-swap-oob="outerHTML"`.
3. The viewer is not replaced, so the optimistic state survives the successful
   response.
4. On a non-2xx response the component reverts the local state and shows a
   visible error alert in the viewer.

The flag endpoint returns `503` for mail failures instead of the normal `200`
error partial. A `2xx` error fragment would look successful to the optimistic
component and prevent the revert. The standalone full-page route adds a hidden
`standalone=1` field; that branch returns `204` because the page has no list row
for an OOB swap.

Opening an unseen message still sends the automatic `read` action on load. The
component marks the message seen locally when the request starts, disables the
read control while that request is in flight, and restores the previous state if
the request fails.

## Tests

- `apps/mail/tests/test_views.py` covers the palette branches, mobile `view`
  selection, optimistic-form markers, the OOB-only flag response, and failure
  status.
- `tests/test_templates.py` continues to reject inline scripts, inline styles,
  `hx-on`, and `hx-vals="js:"`.
- `tests/test_csp.py` keeps `unsafe-eval` and `unsafe-inline` out of the policy.

## Evidence

- `docs/upstream/migracion-django-fase3.md` §4.4 (responsive panel selection
  and folder dialog), §5.3 (OOB swaps and `hx-swap="none"`), §7.4 (shortcuts
  dialog), and §8.4 (keyboard map).
- `docs/upstream/migracion-django-fase3.md` §6.3 (folder-scoped search reused by
  the palette).
