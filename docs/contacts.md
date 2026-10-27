# Contacts module (`apps/contacts/` — RFC 7095 jCard)

DjWebmail provides a per-account address book backed by PostgreSQL and the
**jCard (RFC 7095)** JSON representation of vCard 4.0.

## Upstream evidence and specification

- `dev/DAV/JCard.js:1-227` — SnappyMail's client-side RFC 7095 jCard parser and
  formatter (`["vcard", [["version", {}, "text", "4.0"], ...]]`).
- `snappymail/v/0.0.0/app/libraries/RainLoop/Providers/AddressBook/Classes/Contact.php:7-91`
  — server-side contact entity storing `vCard` properties (`UID`, `FN`, `N`,
  `EMAIL`, `TEL`, `ORG`, `TITLE`, `CATEGORIES`, `NOTE`) and exporting/importing
  jCard (`exportJCard` / `importJCard`).
- `docs/upstream/migracion-django-fase0-2.md:856, 1080` — architectural plan
  placing per-account contacts in PostgreSQL while keeping mail in IMAP.

## Canonical RFC 7095 jCard structure

Every `Contact` row in `apps/contacts/models.py` stores indexed columns for fast
lookup (`account_key`, `full_name`, `primary_email`, `organization`, `category`)
alongside the canonical RFC 7095 `jcard` `JSONField`:

```json
[
  "vcard",
  [
    ["version", {}, "text", "4.0"],
    ["uid", {}, "text", "f81d4fae-7dec-11d0-a765-00a0c91e6bf6"],
    ["fn", {}, "text", "Ada Lovelace"],
    ["n", {}, "text", ["Lovelace", "Ada", "", "", ""]],
    ["email", {"type": "internet"}, "text", "ada@example.org"],
    ["tel", {"type": "voice"}, "text", "+44 20 7946 0999"],
    ["org", {}, "text", "Analytical Engine Group"],
    ["title", {}, "text", "Chief Mathematician"],
    ["categories", {}, "text", "Colleagues"],
    ["note", {}, "text", "Pioneer of computer programming."]
  ]
]
```

`apps/contacts/jcard.py` provides:

- `build_jcard(ContactData) -> list[Any]` — builds a compliant RFC 7095 `vcard`
  component array with `version = "4.0"`.
- `parse_jcard(raw) -> ContactData` — validates component name (`"vcard"`),
  version (`"4.0"`), property tuples (`[name, params, type, value]`), and email
  format, returning normalized `ContactData`.
- `parse_jcard_stream(raw_json) -> list[ContactData]` — accepts either a single
  RFC 7095 `["vcard", [...]]` array or a JSON list of `vcard` arrays.

## Routes and user workflows

| Route | Name | Purpose |
|---|---|---|
| `GET /contacts/` | `contacts:index` | Address book directory, HTMX search (`?q=`), edit (`?edit=<id>`), and sender prefill (`?sender=`) |
| `POST /contacts/save/` | `contacts:create` | Create a contact and synchronize its RFC 7095 `jcard` |
| `POST /contacts/<id>/save/` | `contacts:update` | Update an existing contact and synchronize its RFC 7095 `jcard` |
| `POST /contacts/<id>/delete/` | `contacts:delete` | Delete a contact scoped to `account_key` |
| `GET /contacts/export.json` | `contacts:export_jcard` | Download all account contacts as `application/vcard+json` |
| `POST /contacts/import/` | `contacts:import_jcard` | Import a `.json` jCard file or pasted JSON payload (upserting by email per account) |

### Integration with Compose and Message Viewer

1. **Compose from Contacts**: Every contact card includes a **Compose** button
   linking to `/compose/?to=Full+Name+%3Cemail%40example.org%3E`.
2. **Recipient autocomplete in Compose**: `/compose/`, `/compose/reply/...`,
   `/compose/reply-all/...`, and `/compose/forward/...` populate
   `<datalist id="contact-suggestions">` for the `To`, `Cc`, and `Bcc` inputs
   using `list_contact_suggestions(account_key)`.
3. **Save contact from Message Viewer**: Opening any message shows a
   **+ Save contact** action next to the sender's address that opens
   `/contacts/?sender=...` with the sender's display name and email prefilled.
