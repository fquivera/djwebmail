"""Tests for internationalization catalogs and UTF-8 encoding integrity."""

from __future__ import annotations

import gettext

from django.conf import settings
from django.utils import translation


def test_spanish_mo_catalog_has_no_mojibake() -> None:
    mo_path = settings.BASE_DIR / "locale" / "es" / "LC_MESSAGES" / "django.mo"
    assert mo_path.is_file(), "Compiled django.mo catalog must exist"

    with open(mo_path, "rb") as f:
        translations = gettext.GNUTranslations(f)
        catalog = getattr(translations, "_catalog", {})

    assert len(catalog) > 100
    for msgid, msgstr in catalog.items():
        assert "Ã" not in msgstr, f"Mojibake detected in translation for '{msgid}': '{msgstr}'"
        assert "Â" not in msgstr, f"Mojibake detected in translation for '{msgid}': '{msgstr}'"


def test_spanish_common_translations_rendered_accurately() -> None:
    with translation.override("es"):
        assert translation.gettext("Email address") == "Dirección de correo electrónico"
        assert translation.gettext("All rights reserved.") == "Todos los derechos reservados."
        assert translation.gettext("About DjWebmail") == "Acerca de DjWebmail"
        assert (
            translation.gettext("Enter a valid email address.")
            == "Introduzca una dirección de correo electrónico válida."
        )
