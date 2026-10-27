"""RFC 7095 (jCard) serializer, parser, and validator.

jCard is the JSON format for vCard 4.0 defined in RFC 7095:
``["vcard", [[name, params, type, value], ...]]``.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from email.header import decode_header, make_header
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.contacts.constants import (
    CONTACT_CATEGORY_MAX_LENGTH,
    CONTACT_NAME_MAX_LENGTH,
    CONTACT_NOTE_MAX_LENGTH,
    CONTACT_ORG_MAX_LENGTH,
    CONTACT_PHONE_MAX_LENGTH,
    CONTACT_TITLE_MAX_LENGTH,
    JCARD_COMPONENT,
    JCARD_VERSION,
)


@dataclass(frozen=True)
class ContactData:
    """Typed contact fields extracted from or serialized into an RFC 7095 jCard."""

    full_name: str
    email: str
    uid: str = ""
    phone: str = ""
    organization: str = ""
    job_title: str = ""
    category: str = ""
    notes: str = ""


def decode_mime_text(value: str) -> str:
    """Decode RFC 2047 encoded-words (``=?utf-8?q?...?=``) into clean Unicode text."""
    text = value.replace("\r", " ").replace("\n", " ").strip()
    if "=?" not in text:
        return text
    try:
        return str(make_header(decode_header(text))).strip()
    except Exception:
        return text


def build_jcard(data: ContactData) -> list[Any]:
    """Build a canonical RFC 7095 jCard array from ``data``."""
    clean_uid = data.uid.strip() or str(uuid.uuid4())
    clean_name = decode_mime_text(data.full_name)[:CONTACT_NAME_MAX_LENGTH]
    clean_email = data.email.strip().lower()
    if not clean_name:
        clean_name = clean_email.split("@", 1)[0]

    given_name, _, surname = clean_name.partition(" ")
    structured_name = [
        surname.strip(),
        given_name.strip(),
        "",
        "",
        "",
    ]

    properties: list[list[Any]] = [
        ["version", {}, "text", JCARD_VERSION],
        ["uid", {}, "text", clean_uid],
        ["fn", {}, "text", clean_name],
        ["n", {}, "text", structured_name],
        ["email", {"type": "internet"}, "text", clean_email],
    ]

    clean_phone = data.phone.strip()[:CONTACT_PHONE_MAX_LENGTH]
    if clean_phone:
        properties.append(["tel", {"type": "cell"}, "text", clean_phone])

    clean_org = data.organization.strip()[:CONTACT_ORG_MAX_LENGTH]
    if clean_org:
        properties.append(["org", {}, "text", clean_org])

    clean_title = data.job_title.strip()[:CONTACT_TITLE_MAX_LENGTH]
    if clean_title:
        properties.append(["title", {}, "text", clean_title])

    clean_category = data.category.strip()[:CONTACT_CATEGORY_MAX_LENGTH]
    if clean_category:
        properties.append(["categories", {}, "text", clean_category])

    clean_notes = data.notes.strip()[:CONTACT_NOTE_MAX_LENGTH]
    if clean_notes:
        properties.append(["note", {}, "text", clean_notes])

    return [JCARD_COMPONENT, properties]


def parse_jcard(payload: Any) -> ContactData:
    """Validate an RFC 7095 jCard array and return its extracted ``ContactData``."""
    if not isinstance(payload, list) or len(payload) != 2:
        raise ValueError("jCard must be a two-element ['vcard', properties] array")

    component, raw_props = payload
    if not isinstance(component, str) or component.lower() != JCARD_COMPONENT:
        raise ValueError("jCard component identifier must be 'vcard'")
    if not isinstance(raw_props, list):
        raise ValueError("jCard properties must be a list")

    has_version_4 = False
    uid_val = ""
    fn_val = ""
    n_fallback = ""
    email_val = ""
    phone_val = ""
    org_val = ""
    title_val = ""
    category_val = ""
    note_val = ""

    for item in raw_props:
        if not isinstance(item, list) or len(item) < 4:
            raise ValueError("Each jCard property must have at least 4 elements")
        prop_name, prop_params, prop_type, prop_value = item[0], item[1], item[2], item[3]
        if not isinstance(prop_name, str) or not isinstance(prop_params, dict):
            raise ValueError("Invalid jCard property header")
        if not isinstance(prop_type, str):
            raise ValueError("Invalid jCard property value type")

        key = prop_name.lower()
        if key == "version" and prop_value == JCARD_VERSION:
            has_version_4 = True
        elif key == "uid" and isinstance(prop_value, str) and not uid_val:
            uid_val = prop_value.strip()
        elif key == "fn" and isinstance(prop_value, str) and not fn_val:
            fn_val = prop_value.strip()
        elif key == "n" and isinstance(prop_value, list) and not n_fallback:
            parts = [str(part).strip() for part in prop_value[:2] if str(part).strip()]
            n_fallback = " ".join(reversed(parts)).strip()
        elif key == "email" and isinstance(prop_value, str) and not email_val:
            email_val = prop_value.strip().lower()
        elif key == "tel" and isinstance(prop_value, str) and not phone_val:
            phone_val = prop_value.strip()
        elif key == "org" and not org_val:
            if isinstance(prop_value, list) and prop_value:
                org_val = str(prop_value[0]).strip()
            elif isinstance(prop_value, str):
                org_val = prop_value.strip()
        elif key == "title" and isinstance(prop_value, str) and not title_val:
            title_val = prop_value.strip()
        elif key == "categories" and isinstance(prop_value, str) and not category_val:
            category_val = prop_value.strip()
        elif key == "note" and isinstance(prop_value, str) and not note_val:
            note_val = prop_value.strip()

    if not has_version_4:
        raise ValueError("jCard must include version 4.0")
    if not email_val:
        raise ValueError("jCard must include at least one email property")
    try:
        validate_email(email_val)
    except ValidationError as exc:
        raise ValueError("jCard email property is not a valid email address") from exc

    resolved_name = decode_mime_text(fn_val or n_fallback or email_val.split("@", 1)[0])[
        :CONTACT_NAME_MAX_LENGTH
    ]
    resolved_uid = uid_val or str(uuid.uuid4())
    return ContactData(
        uid=resolved_uid,
        full_name=resolved_name,
        email=email_val,
        phone=phone_val[:CONTACT_PHONE_MAX_LENGTH],
        organization=org_val[:CONTACT_ORG_MAX_LENGTH],
        job_title=title_val[:CONTACT_TITLE_MAX_LENGTH],
        category=category_val[:CONTACT_CATEGORY_MAX_LENGTH],
        notes=note_val[:CONTACT_NOTE_MAX_LENGTH],
    )


def parse_jcard_stream(raw_json: str) -> list[ContactData]:
    """Parse a JSON string containing one RFC 7095 jCard or an array of jCards."""
    try:
        decoded = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON document") from exc

    if not isinstance(decoded, list) or not decoded:
        raise ValueError("Expected a jCard array or a list of jCards")

    if isinstance(decoded[0], str) and decoded[0].lower() == JCARD_COMPONENT:
        return [parse_jcard(decoded)]

    contacts: list[ContactData] = []
    for entry in decoded:
        contacts.append(parse_jcard(entry))
    if not contacts:
        raise ValueError("No jCard contacts found in payload")
    return contacts
