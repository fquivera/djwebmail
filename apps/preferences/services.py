"""Read and apply per-account presentation preferences."""

from __future__ import annotations

from typing import Any, cast

import nh3
from django.http import HttpRequest
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from apps.accounts.constants import (
    SESSION_ACCOUNT_LABEL_KEY,
    SESSION_DENSITY_KEY,
    SESSION_DISPLAY_NAME_KEY,
    SESSION_LANGUAGE_KEY,
    SESSION_NOTIFICATION_SOUND_ENABLED_KEY,
    SESSION_NOTIFICATIONS_ENABLED_KEY,
    SESSION_PAGE_SIZE_KEY,
    SESSION_REMOTE_IMAGES_KEY,
    SESSION_SIGNATURE_KEY,
    SESSION_THEME_KEY,
    SESSION_TIMEZONE_KEY,
)
from apps.accounts.exceptions import MailSessionError
from apps.preferences.models import (
    AccountSignature,
    BlockedSender,
    BlockedSenderAction,
    MailPreference,
    TrustedSender,
)

SIGNATURE_ALLOWED_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "div",
    "em",
    "font",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "s",
    "small",
    "span",
    "strike",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}

SIGNATURE_ALLOWED_ATTRIBUTES = {
    tag: {"style", "class", "width", "height", "align", "valign", "color", "face", "size"}
    for tag in SIGNATURE_ALLOWED_TAGS
}
SIGNATURE_ALLOWED_ATTRIBUTES["a"] = {"href", "title", "target", "style", "class"}
SIGNATURE_ALLOWED_ATTRIBUTES["img"] = {"src", "alt", "title", "width", "height", "style", "class"}


def sanitize_signature_html(html: str) -> str:
    """Sanitize signature HTML to allow rich formatting while preventing XSS."""
    if not html:
        return ""
    cleaned = nh3.clean(
        html,
        tags=SIGNATURE_ALLOWED_TAGS,
        attributes=SIGNATURE_ALLOWED_ATTRIBUTES,
        url_schemes={"http", "https", "mailto", "tel", "data", "cid"},
        link_rel="noopener noreferrer",
    )
    return cleaned


def get_mail_preference(request: HttpRequest) -> MailPreference:
    """Return the preference row for the authenticated account."""
    account = getattr(request, "mail_account", None)
    if account is None:
        raise MailSessionError("No authenticated mail account on this request")
    preference, _created = cast(Any, MailPreference).objects.get_or_create(
        account_key=account.account_key,
        defaults={"email": account.email},
    )
    return preference


def apply_mail_preference(request: HttpRequest, preference: MailPreference) -> None:
    """Copy the saved choices into the session and activate locale settings."""
    session = _session(request)
    session[SESSION_LANGUAGE_KEY] = preference.language
    session[SESSION_THEME_KEY] = preference.theme
    session[SESSION_DENSITY_KEY] = preference.density
    session[SESSION_TIMEZONE_KEY] = preference.timezone
    session[SESSION_PAGE_SIZE_KEY] = preference.page_size
    session[SESSION_REMOTE_IMAGES_KEY] = preference.remote_images
    default_sig = get_default_signature(preference.account_key)
    sig_content = default_sig.content_html if default_sig else preference.signature_html
    session[SESSION_SIGNATURE_KEY] = sig_content
    session[SESSION_DISPLAY_NAME_KEY] = preference.display_name
    session[SESSION_ACCOUNT_LABEL_KEY] = preference.account_label
    session[SESSION_NOTIFICATIONS_ENABLED_KEY] = preference.notifications_enabled
    session[SESSION_NOTIFICATION_SOUND_ENABLED_KEY] = preference.notification_sound_enabled
    translation.activate(preference.language)
    setattr(request, "LANGUAGE_CODE", preference.language)  # noqa: B010
    try:
        timezone.activate(preference.timezone)
    except (KeyError, ValueError):
        timezone.deactivate()


def _session(request: HttpRequest) -> Any:
    return cast(Any, request).session


def get_account_signatures(
    account_key: str,
    *,
    email: str = "",
    seed_from_pref: str = "",
) -> list[AccountSignature]:
    """Return all signatures for the account, migrating legacy signature if needed."""
    qs = cast(Any, AccountSignature).objects.filter(account_key=account_key)
    signatures = list(qs)
    if not signatures and seed_from_pref.strip():
        migrated = cast(Any, AccountSignature).objects.create(
            account_key=account_key,
            email=email,
            name=_("Default signature"),
            content_html=sanitize_signature_html(seed_from_pref),
            is_default=True,
            is_active=True,
        )
        signatures = [migrated]
    return signatures


def get_active_signatures(
    account_key: str,
    *,
    email: str = "",
    seed_from_pref: str = "",
) -> list[AccountSignature]:
    """Return only active signatures for the compose picker."""
    all_sigs = get_account_signatures(
        account_key,
        email=email,
        seed_from_pref=seed_from_pref,
    )
    return [s for s in all_sigs if s.is_active]


def get_default_signature(account_key: str) -> AccountSignature | None:
    """Return the active default signature if one exists."""
    return (
        cast(Any, AccountSignature)
        .objects.filter(
            account_key=account_key,
            is_default=True,
            is_active=True,
        )
        .first()
    )


def sync_default_signature_to_session(request: HttpRequest) -> None:
    """Ensure the session and MailPreference mirror the active default signature."""
    account = getattr(request, "mail_account", None)
    if not account:
        return
    default_sig = get_default_signature(account.account_key)
    sig_content = default_sig.content_html if default_sig else ""
    session = _session(request)
    session[SESSION_SIGNATURE_KEY] = sig_content

    cast(Any, MailPreference).objects.filter(
        account_key=account.account_key,
    ).update(signature_html=sig_content)


def extract_sender_address_and_domain(sender_header: str) -> tuple[str, str]:
    """Extract normalized email address and domain from an RFC 5322 From header."""
    from email.utils import parseaddr

    _, address = parseaddr(sender_header or "")
    clean_addr = address.strip().lower()
    domain = clean_addr.split("@")[-1] if "@" in clean_addr else ""
    return clean_addr, domain


def is_sender_trusted(account_key: str, sender_header: str) -> bool:
    """Check if a sender email address or domain is in the account's trusted allowlist."""
    if not account_key or not sender_header:
        return False
    address, domain = extract_sender_address_and_domain(sender_header)
    patterns = [p for p in (address, domain) if p]
    if not patterns:
        return False
    return (
        cast(Any, TrustedSender)
        .objects.filter(
            account_key=account_key,
            pattern__in=patterns,
        )
        .exists()
    )


def is_sender_blocked(account_key: str, sender_header: str) -> BlockedSender | None:
    """Check if a sender email address or domain is in the account's blocked denylist."""
    if not account_key or not sender_header:
        return None
    address, domain = extract_sender_address_and_domain(sender_header)
    patterns = [p for p in (address, domain) if p]
    if not patterns:
        return None
    return (
        cast(Any, BlockedSender)
        .objects.filter(
            account_key=account_key,
            pattern__in=patterns,
        )
        .first()
    )


def get_trusted_senders(account_key: str) -> list[TrustedSender]:
    """Return all trusted sender patterns for the account."""
    return list(
        cast(Any, TrustedSender).objects.filter(account_key=account_key).order_by("pattern")
    )


def get_blocked_senders(account_key: str) -> list[BlockedSender]:
    """Return all blocked sender patterns for the account."""
    return list(
        cast(Any, BlockedSender).objects.filter(account_key=account_key).order_by("pattern")
    )


def add_trusted_sender(
    account_key: str,
    email: str,
    pattern: str,
    description: str = "",
) -> TrustedSender:
    """Add or update a trusted sender pattern."""
    norm_pattern = pattern.strip().lower().lstrip("@")
    sender, _ = cast(Any, TrustedSender).objects.update_or_create(
        account_key=account_key,
        pattern=norm_pattern,
        defaults={"email": email, "description": description.strip()},
    )
    return sender


def delete_trusted_sender(account_key: str, pk: int) -> bool:
    """Delete a trusted sender entry by primary key."""
    deleted, _ = (
        cast(Any, TrustedSender)
        .objects.filter(
            account_key=account_key,
            pk=pk,
        )
        .delete()
    )
    return bool(deleted)


def add_blocked_sender(
    account_key: str,
    email: str,
    pattern: str,
    action: str = BlockedSenderAction.TRASH,
    description: str = "",
) -> BlockedSender:
    """Add or update a blocked sender pattern."""
    norm_pattern = pattern.strip().lower().lstrip("@")
    sender, _ = cast(Any, BlockedSender).objects.update_or_create(
        account_key=account_key,
        pattern=norm_pattern,
        defaults={
            "email": email,
            "action": action,
            "description": description.strip(),
        },
    )
    return sender


def delete_blocked_sender(account_key: str, pk: int) -> bool:
    """Delete a blocked sender entry by primary key."""
    deleted, _ = (
        cast(Any, BlockedSender)
        .objects.filter(
            account_key=account_key,
            pk=pk,
        )
        .delete()
    )
    return bool(deleted)
