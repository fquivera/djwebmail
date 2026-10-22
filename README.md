# DjWebmail

**A modern, HTMX-driven webmail client built with Django.**

DjWebmail is a lightweight, self-hosted webmail frontend that talks to your
existing IMAP/SMTP server. It is inspired by [SnappyMail](https://github.com/the-djmaze/snappymail)
but rewritten from scratch in Django with a server-rendered, HTMX-first
architecture — no SPA, no heavy JavaScript framework, no build step required
to run it.

> **Status:** early development. The architecture is being designed in the open;
> APIs and templates will change. Watch the repo or open an issue to follow along.

---

## Why another webmail?

Most self-hosted webmail clients are either PHP applications (Roundcube,
SnappyMail) or single-page apps with large JavaScript bundles. DjWebmail takes
a different path:

- **Server-rendered HTML** with [HTMX](https://htmx.org/) for partial updates.
- **Alpine.js** for local UI state only (menus, modals, toggles).
- **Tailwind CSS + daisyUI** for a compact, information-dense interface with
  light and dark themes.
- **Django** for the backend: clear app boundaries, testable service layer,
  standard security middleware, and a familiar developer experience.

The goal is a webmail that is fast on modest hardware, easy to audit, and
pleasant to extend for Django developers.

---

## Stack

| Layer      | Choice                                  | Why |
|------------|-----------------------------------------|-----|
| Backend    | Django (LTS)                            | Mature, secure, well-documented |
| IMAP/SMTP  | `imapclient` + `smtplib`                | Explicit, testable, no ORM coupling |
| Templates  | Django templates + partials             | Server-rendered, easy to reason about |
| Interactivity | HTMX                                 | Partial updates without a SPA |
| Local UI state | Alpine.js                           | Small, declarative, no build step |
| Styling    | Tailwind CSS + daisyUI                  | Utility-first, themeable, dark mode |
| Config     | `django-environ`                        | 12-factor settings per environment |

---

## Design principles

1. **The server owns the state.** HTMX requests return HTML fragments; the
   browser does not orchestrate data fetching.
2. **Alpine is for UI only.** No Alpine component talks to the network directly.
3. **IMAP is the source of truth.** DjWebmail stores as little as possible in
   the database — ideally only user preferences and UI cache. Mail lives on
   your IMAP server.
4. **No hidden magic.** Service classes are plain Python; views are thin;
   templates are readable.
5. **Security by default.** CSRF, CSP, secure cookies, and explicit
   authentication against IMAP — no silent fallbacks.

---

## Architecture (planned)

```text
djwebmail/
├── config/           # Settings package, URLs, ASGI/WSGI
├── apps/
│   ├── accounts/     # IMAP/SMTP login, session handling
│   ├── mail/         # Folders, message list, message view
│   ├── compose/      # Compose, reply, forward, send
│   └── preferences/  # Per-user UI preferences
└── common/           # Shared services, templatetags, base templates
```

The `ImapService` class encapsulates connection and operations, so views and
HTMX endpoints stay thin and testable.

---

## Getting started (development)

> Placeholder — will be updated as the project takes shape.

```bash
git clone https://github.com/<your-org>/djwebmail.git
cd djwebmail
# Install uv if missing: https://docs.astral.sh/uv/getting-started/installation/
uv sync
cp .env.example .env   # set your IMAP/SMTP credentials
uv run python manage.py migrate
uv run python manage.py runserver
```
Node.js is only needed if you rebuild the Tailwind CSS bundle
`(npm install && npm run build:css)`. The compiled CSS is committed so the app
runs without Node.

## Inspiration and credit
`DjWebmail` is inspired by [SnappyMail](https://snappymail.eu/),
a fast PHP webmail client. We are grateful to its authors and community for
showing what a lean webmail can feel like.

**DjWebmail** is **an independent project** and is **not affiliated with, endorsed by, or a fork** of `SnappyMail`. It does not share code with SnappyMail; it is a from-scratch Django implementation.

## Contributing
Contributions are welcome — issues, discussions, and pull requests.

- Please open an issue before starting significant work, so we can align on
direction.
- Follow the existing code style (Ruff lint + format, pyright, Django conventions).
- Add tests for new behavior where practical.
- Be kind. See CODE_OF_CONDUCT.md (adopting the Contributor Covenant).

### License
MIT — see the LICENSE file for details.

## Roadmap (high level)
□ IMAP login and session management  
□ Folder tree and message list with HTMX pagination  
□ Message viewer with safe HTML rendering and remote-content blocking  
□ Compose, reply, forward, send via SMTP  
□ Per-user UI preferences (theme, density, signature)  
□ Search across folders  
□ Accessibility pass and keyboard shortcuts  
□ Docker image and deployment guide  

## Acknowledgements
Built with Django, HTMX,
Alpine.js, Tailwind CSS,
and daisyUI.