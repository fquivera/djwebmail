---
name: i18n
description: Internationalization rules for DjWebmail. Use when adding user-facing text, templates, forms, emails, validation errors, date/number formatting, language preferences, or translation catalogs.
---

# Internationalization (i18n)

DjWebmail ships English source strings and Spanish as the first translation.
Every user-facing string must be translatable from day one; adding a language
later must not require touching application code.

## Principles

1. **English source language.** Write identifiers, comments, commit messages,
   and source strings in English. Translations live in `locale/`.
2. **No user-facing literals.** Templates, views, forms, services, emails, and
   JavaScript messages use `gettext`/`{% translate %}`, never raw text.
3. **Translate at the edge.** Logs, audit events, metric names, URL names,
   database codes, and API error identifiers stay stable English. Translate the
   human message that wraps them.
4. **User content is never translated.** Subjects, bodies, folder names, and
   signatures are data.
5. **One string, one message.** Do not build sentences by concatenation; use
   placeholders and let translators reorder.

## Locales and settings

```python
# config/settings/base.py
LANGUAGE_CODE = env.str("DJANGO_LANGUAGE_CODE", default="en-us")
LANGUAGES = [("en", "English"), ("es", "Spanish")]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True
```

`LocaleMiddleware` sits after `SessionMiddleware` and before
`CommonMiddleware`:

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    # ...
]
```

`LANGUAGE_CODE` is the fallback for anonymous users and missing translations,
not a per-user preference.

## Python API

```python
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.utils.translation import ngettext, pgettext

# Runtime code: request, view, service called per request.
message = _("Message moved to Trash.")

# Import time, models, forms, settings, constants.
class MailFolder(models.TextChoices):
    INBOX = "INBOX", _lazy("Inbox")

# Plurals: never branch on == 1.
count = 3
message = ngettext("%(count)s message", "%(count)s messages", count) % {"count": count}

# Ambiguous words get context for translators.
label = pgettext("verb", "Post")
```

- Use named placeholders (`%(name)s`), never positional `%s`.
- Never interpolate a lazy string with an f-string; cast first:
  `str(_lazy("Inbox"))`.
- `gettext_lazy` is for values evaluated later. Do not use it in a request path
  where a plain string is enough.
- Do not translate exception classes or internal error codes. Translate the
  message rendered to the user.

## Templates

```django
{% load i18n %}

<title>{% translate "DjWebmail" %}</title>

{% blocktranslate trimmed with count=unread_count %}
  You have {{ count }} unread message.
{% plural %}
  You have {{ count }} unread messages.
{% endblocktranslate %}

<a href="{% url 'mail:folder' folder.name %}">
  {% translate "Open folder" %}
</a>
```

- `{% translate %}` for fixed strings; `{% blocktranslate %}` when there are
  variables or plurals.
- Use `trimmed` to avoid stray whitespace in translated output.
- Never wrap variables in `{% translate %}`; translate only literals.
- `{% get_current_language as LANGUAGE_CODE %}` is available for `<html lang>`
  and `dir` attributes.
- Keep brand names ("DjWebmail", "IMAP", "SMTP") untranslated unless the
  translator explicitly localizes them.

## Per-user language

The preference belongs to the user, not to the deployment:

1. Add `language` to the preferences model with choices from `settings.LANGUAGES`
   and a default from `settings.LANGUAGE_CODE`.
2. On login, persist the preference and store the language code in the mail
   session under `mail_language`. Django 5's `set_language` only writes a cookie,
   so it cannot replace the per-account preference.
3. `LocaleMiddleware` runs before the mail session is hydrated, so
   `MailSessionMiddleware` (after `AuthenticationMiddleware`) calls
   `translation.activate(mail_language)` and updates `request.LANGUAGE_CODE`.
4. Persist the choice, but never store translated labels in the database — store
   the language code.

Language switcher:

```python
# config/urls.py
path("i18n/", include("django.conf.urls.i18n")),
```

```django
<form action="{% url 'set_language' %}" method="post">
  {% csrf_token %}
  <input type="hidden" name="next" value="{{ request.path }}">
  <select name="language">
    {% get_available_languages as languages %}
    {% for code, name in languages %}
      <option value="{{ code }}" {% if code == LANGUAGE_CODE %}selected{% endif %}>
        {{ name }}
      </option>
    {% endfor %}
  </select>
  <button type="submit">{% translate "Change language" %}</button>
</form>
```

## Dates, numbers, and time zones

- Keep `USE_TZ = True`; store UTC, render in the user's time zone.
- Add `timezone` to preferences; activate it per request with
  `timezone.activate(user.timezone)` and deactivate it in middleware `finally`.
- Use localized formats, not hardcoded patterns:
  `{{ value|date:"SHORT_DATE_FORMAT" }}`, `{{ value|time:"SHORT_TIME_FORMAT" }}`,
  `{{ value|floatformat }}`.
- For custom formats, use `FORMAT_MODULE_PATH` with per-locale format modules.
- Relative times ("3 minutes ago") need a translatable formatter; do not build
  them with string concatenation.

## Emails and notifications

Render with the recipient's language, not the request language:

```python
from django.utils import translation

with translation.override(user.language):
    subject = _("Your message was sent")
    body = render_to_string("mail/emails/sent.txt", context, request=None)
```

- Translate subject, body, and plain-text alternative.
- Keep links and technical identifiers out of translation memory.
- Queue emails with the language code stored alongside the message.

## JavaScript and HTMX

- Prefer server-rendered partials: HTMX responses already carry translated HTML.
- For client-side messages, expose translations as data, never inline script
  (CSP forbids it):

```django
{{ translations|json_script:"i18n" }}
```

```javascript
const messages = JSON.parse(document.getElementById("i18n").textContent);
```

- Use Django's `JavaScriptCatalog` only if a large JS surface needs it; it adds a
  view and a script payload.
- `data-*` attributes can carry translated labels for Alpine components.
- Never format dates or numbers in JavaScript with hardcoded patterns.

## Catalogs

```bash
uv run python manage.py makemessages -l es
uv run python manage.py compilemessages
```

- A language switcher must update `MailPreference.language` and the
  `mail_language` session key; a cookie-only switch is overwritten by the
  account preference.
- Requires GNU gettext (`xgettext`, `msgfmt`) to regenerate the catalog.
- Commit both `locale/es/LC_MESSAGES/django.po` and the compiled
  `locale/es/LC_MESSAGES/django.mo`. The runtime image and the test environment
  do not install GNU gettext, so the compiled catalog must be present in the
  checkout.
- After changing source strings, regenerate and compile the catalog in the same
  commit:
- CI verifies the catalog is current:

```bash
uv run python manage.py makemessages --all --ignore=.venv --ignore=docs
git diff --exit-code -- locale/
```

- A translation is reviewed like code: no machine output pasted unreviewed, no
  changed placeholders, no missing plural forms.
- Do not edit `.po` files to match broken source; fix the source string.

## Testing

```python
from django.utils import translation

def test_login_error_is_translated(client):
    with translation.override("es"):
        response = client.post("/login/", {"email": "", "password": ""})
    assert "obligatorio" in response.content.decode()
```

- Test at least one translated string per feature and the fallback to English.
- Test pluralization for a language with different plural rules when adding one.
- Test that the language switcher persists the choice for authenticated users.
- Test emails with `translation.override`; assert subject and body language.

## Anti-Patterns

- Literal UI text in templates, views, forms, or services
- `_()` around variables or already-translated strings
- f-strings with `gettext_lazy` objects
- Concatenated sentences (`_("Hello ") + name`)
- Positional placeholders (`%s`) that translators can reorder incorrectly
- Translating logs, audit keys, metric names, or URL names
- Storing translated labels in the database instead of language codes
- Hardcoded date/time/number formats
- Assuming every language has two plural forms
- Using `LANGUAGE_CODE` as the user preference
- Editing `.po` files without updating the source string
- Loading a translation catalog from an untrusted source at runtime

## Integration with Other Skills

- **django-templates**: template structure and partials that host translated text
- **django-forms**: `gettext_lazy` labels, help text, and validation messages
- **htmx-patterns**: translated partials and `HX-Trigger` messages
- **configuration**: language defaults and per-user preferences boundaries
- **pytest-django-patterns**: translation and language-switch tests
- **django-expert**: security and deployment implications of locale files
