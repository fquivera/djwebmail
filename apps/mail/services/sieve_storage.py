"""Unified Sieve script storage service with ManageSieve and Database fallback.

When a ManageSieve daemon (Dovecot Pigeonhole / Cyrus) is reachable on the server,
rules are compiled and pushed via RFC 5804 so that the MDA filters incoming messages
on arrival. When unavailable, rules are persisted in the database model `UserSieveScript`.
"""

from __future__ import annotations

import logging
import socket
from collections.abc import Sequence
from typing import Any, cast

from django.conf import settings
from django.http import HttpRequest

from apps.accounts.services.account import MailAccount
from apps.accounts.services.session import get_mail_session_password
from apps.mail.models import UserSieveScript
from apps.mail.services.managesieve import (
    DEFAULT_MANAGESIEVE_PORT,
    ManageSieveAuthError,
    ManageSieveClient,
    ManageSieveConnectionError,
    ManageSieveError,
)
from apps.mail.services.sieve_generator import (
    BlockedSenderRule,
    FilterRule,
    VacationRule,
    rules_to_sieve_script,
    sieve_script_to_rules,
    sieve_script_to_vacation,
)

DEFAULT_SCRIPT_NAME = "djwebmail"

logger = logging.getLogger(__name__)


def get_managesieve_settings() -> tuple[str, int, str, bool]:
    """Return configured host, port, security mode, and enabled flag."""
    host = getattr(settings, "MAIL_MANAGESIEVE_HOST", "")
    port = getattr(settings, "MAIL_MANAGESIEVE_PORT", DEFAULT_MANAGESIEVE_PORT)
    security = getattr(settings, "MAIL_MANAGESIEVE_SECURITY", "starttls")
    enabled = getattr(settings, "MAIL_MANAGESIEVE_ENABLED", True)
    return host, port, security, enabled


def is_managesieve_online(host: str, port: int, timeout: int = 2) -> bool:
    """Perform a fast socket probe to check if the ManageSieve daemon is reachable."""
    if not host:
        return False
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return True
    except OSError:
        return False


def get_account_managesieve_client(
    request: HttpRequest,
    account: MailAccount,
) -> ManageSieveClient | None:
    """Initialize an authenticated ManageSieveClient if configured and reachable."""
    configured_host, port, security, enabled = get_managesieve_settings()
    if not enabled:
        return None

    host = configured_host or account.imap_host
    if not host:
        return None

    try:
        password = get_mail_session_password(request)
    except Exception as exc:
        logger.warning("ManageSieve: could not obtain session password: %s", exc)
        return None

    try:
        client = ManageSieveClient(
            host=host,
            port=port,
            security=security,
            verify_tls=getattr(settings, "MAIL_VERIFY_TLS", True),
            timeout=getattr(settings, "MAIL_TIMEOUT_SECONDS", 10),
        )
        client.connect()
        client.authenticate(account.email, password)
        return client
    except (ManageSieveConnectionError, ManageSieveAuthError, ManageSieveError) as exc:
        logger.warning("ManageSieve client connection/auth failed for %s: %s", account.email, exc)
        return None


def load_sieve_rules(
    request: HttpRequest,
    account: MailAccount,
) -> tuple[list[FilterRule], list[FilterRule], bool]:
    """Load filter rules for an account.

    Returns:
        (incoming_rules, outgoing_rules, is_synced_to_server)
    """
    # 1. Try ManageSieve if available
    client = get_account_managesieve_client(request, account)
    if client:
        try:
            with client:
                _scripts, active_name = client.list_scripts()
                target_script = active_name or DEFAULT_SCRIPT_NAME
                try:
                    script_content = client.get_script(target_script)
                    incoming = sieve_script_to_rules(script_content)
                    # Outgoing filters stay in local storage as standard Sieve is inbound LDA
                    fallback_record = _get_or_create_db_record(account)
                    outgoing_data = fallback_record.rules_data.get("outgoing", [])
                    outgoing = [
                        FilterRule.from_dict(r) for r in outgoing_data if isinstance(r, dict)
                    ]
                    return incoming, outgoing, True
                except ManageSieveError as exc:
                    logger.warning("ManageSieve get_script failed for %s: %s", target_script, exc)
        except Exception as exc:
            logger.warning("ManageSieve load error for %s: %s", account.email, exc)

    # 2. Fall back to database model
    record = _get_or_create_db_record(account)
    rules_dict = record.rules_data or {}
    incoming_data = rules_dict.get("incoming", [])
    outgoing_data = rules_dict.get("outgoing", [])

    incoming = [FilterRule.from_dict(r) for r in incoming_data if isinstance(r, dict)]
    outgoing = [FilterRule.from_dict(r) for r in outgoing_data if isinstance(r, dict)]
    return incoming, outgoing, False


def get_account_blocked_rules(account_key: str) -> list[BlockedSenderRule]:
    """Retrieve active blocked sender patterns for this account."""
    from apps.preferences.services import get_blocked_senders

    blocked_list = get_blocked_senders(account_key)
    return [BlockedSenderRule(pattern=b.pattern, action=b.action) for b in blocked_list]


def save_sieve_rules(
    request: HttpRequest,
    account: MailAccount,
    incoming_rules: Sequence[FilterRule],
    outgoing_rules: Sequence[FilterRule] = (),
) -> bool:
    """Save filter rules to the database and upload to ManageSieve if online.

    Returns:
        True if synchronized with server ManageSieve, False if saved only in DB fallback.
    """
    incoming_list = list(incoming_rules)
    outgoing_list = list(outgoing_rules)

    # Preserve existing vacation configuration & blocked senders
    vacation_rule, _ = load_vacation_rule(request, account)
    blocked_rules = get_account_blocked_rules(account.account_key)

    sieve_source = rules_to_sieve_script(
        incoming_list,
        script_name=DEFAULT_SCRIPT_NAME,
        vacation=vacation_rule,
        blocked_senders=blocked_rules,
    )

    # 1. Always update database record for parity and offline preservation
    record = _get_or_create_db_record(account)
    record.script_source = sieve_source
    record.rules_data = {
        "incoming": [r.to_dict() for r in incoming_list],
        "outgoing": [r.to_dict() for r in outgoing_list],
        "vacation": vacation_rule.to_dict(),
        "blocked_senders": [b.to_dict() for b in blocked_rules],
    }
    record.is_active = (
        any(r.active for r in incoming_list) or vacation_rule.enabled or bool(blocked_rules)
    )
    record.save()

    # 2. Push to ManageSieve server if online
    client = get_account_managesieve_client(request, account)
    if client:
        try:
            with client:
                client.put_script(DEFAULT_SCRIPT_NAME, sieve_source)
                client.set_active(DEFAULT_SCRIPT_NAME)
                return True
        except ManageSieveError as exc:
            logger.warning("ManageSieve save_sieve_rules failed for %s: %s", account.email, exc)
            return False

    return False


def load_vacation_rule(
    request: HttpRequest,
    account: MailAccount,
) -> tuple[VacationRule, bool]:
    """Load vacation auto-reply configuration for an account.

    Returns:
        (vacation_rule, is_synced_to_server)
    """
    # 1. Try ManageSieve if available
    client = get_account_managesieve_client(request, account)
    if client:
        try:
            with client:
                _scripts, active_name = client.list_scripts()
                target_script = active_name or DEFAULT_SCRIPT_NAME
                try:
                    script_content = client.get_script(target_script)
                    vacation = sieve_script_to_vacation(script_content)
                    if vacation is not None:
                        return vacation, True
                    fallback_record = _get_or_create_db_record(account)
                    raw_vacation = fallback_record.rules_data.get("vacation")
                    if isinstance(raw_vacation, dict):
                        return VacationRule.from_dict(raw_vacation), True
                    return VacationRule(), True
                except ManageSieveError as exc:
                    logger.warning("ManageSieve get_script (vacation) failed: %s", exc)
        except Exception as exc:
            logger.warning("ManageSieve load_vacation_rule error: %s", exc)

    # 2. Fall back to database model
    record = _get_or_create_db_record(account)
    rules_dict = record.rules_data or {}
    raw_vacation = rules_dict.get("vacation")
    if isinstance(raw_vacation, dict):
        return VacationRule.from_dict(raw_vacation), False
    return VacationRule(), False


def save_vacation_rule(
    request: HttpRequest,
    account: MailAccount,
    vacation: VacationRule,
) -> bool:
    """Save vacation configuration to database and push Sieve script to server.

    Returns:
        True if synchronized with server ManageSieve, False if saved only in DB fallback.
    """
    incoming_rules, outgoing_rules, _ = load_sieve_rules(request, account)
    blocked_rules = get_account_blocked_rules(account.account_key)

    sieve_source = rules_to_sieve_script(
        incoming_rules,
        script_name=DEFAULT_SCRIPT_NAME,
        vacation=vacation,
        blocked_senders=blocked_rules,
    )

    # 1. Update database record
    record = _get_or_create_db_record(account)
    record.script_source = sieve_source
    record.rules_data = {
        "incoming": [r.to_dict() for r in incoming_rules],
        "outgoing": [r.to_dict() for r in outgoing_rules],
        "vacation": vacation.to_dict(),
        "blocked_senders": [b.to_dict() for b in blocked_rules],
    }
    record.is_active = (
        any(r.active for r in incoming_rules) or vacation.enabled or bool(blocked_rules)
    )
    record.save()

    # 2. Push to ManageSieve if online
    client = get_account_managesieve_client(request, account)
    if client:
        try:
            with client:
                client.put_script(DEFAULT_SCRIPT_NAME, sieve_source)
                client.set_active(DEFAULT_SCRIPT_NAME)
                return True
        except ManageSieveError as exc:
            logger.warning("ManageSieve save_vacation_rule failed for %s: %s", account.email, exc)
            return False

    return False


def save_blocked_senders_to_sieve(
    request: HttpRequest,
    account: MailAccount,
) -> bool:
    """Recompile and push the active Sieve script with updated blocked senders."""
    incoming_rules, outgoing_rules, _ = load_sieve_rules(request, account)
    vacation_rule, _ = load_vacation_rule(request, account)
    blocked_rules = get_account_blocked_rules(account.account_key)

    sieve_source = rules_to_sieve_script(
        incoming_rules,
        script_name=DEFAULT_SCRIPT_NAME,
        vacation=vacation_rule,
        blocked_senders=blocked_rules,
    )

    # 1. Update database record
    record = _get_or_create_db_record(account)
    record.script_source = sieve_source
    record.rules_data = {
        "incoming": [r.to_dict() for r in incoming_rules],
        "outgoing": [r.to_dict() for r in outgoing_rules],
        "vacation": vacation_rule.to_dict(),
        "blocked_senders": [b.to_dict() for b in blocked_rules],
    }
    record.is_active = (
        any(r.active for r in incoming_rules) or vacation_rule.enabled or bool(blocked_rules)
    )
    record.save()

    # 2. Push to ManageSieve if online
    client = get_account_managesieve_client(request, account)
    if client:
        try:
            with client:
                client.put_script(DEFAULT_SCRIPT_NAME, sieve_source)
                client.set_active(DEFAULT_SCRIPT_NAME)
                return True
        except ManageSieveError as exc:
            logger.warning("ManageSieve save_blocked_senders failed for %s: %s", account.email, exc)
            return False

    return False


def _get_or_create_db_record(account: MailAccount) -> UserSieveScript:
    record, _ = cast(Any, UserSieveScript).objects.get_or_create(
        account_key=account.account_key,
        name=DEFAULT_SCRIPT_NAME,
        defaults={"email": account.email},
    )
    return record
