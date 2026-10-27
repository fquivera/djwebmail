"""Tests for password security validation, hashing, and change drivers."""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from apps.accounts.exceptions import PasswordChangeError, PasswordValidationError
from apps.accounts.services.account import MailAccount
from apps.accounts.services.credentials import CredentialStore
from apps.accounts.services.password import (
    change_account_password,
    hash_sha512_crypt,
    update_accounts_file_password,
    validate_password_rules,
)
from apps.accounts.services.session import (
    start_mail_session,
)

pytestmark = pytest.mark.django_db


def test_validate_password_rules_rejects_weak_passwords() -> None:
    # Too short (< 12)
    assert any("12" in err for err in validate_password_rules("Short1!"))

    # Missing uppercase
    assert any("uppercase" in err for err in validate_password_rules("lowercase12345!"))

    # Missing lowercase
    assert any("lowercase" in err for err in validate_password_rules("UPPERCASE12345!"))

    # Missing number
    assert any("number" in err for err in validate_password_rules("NoNumbersHere!@#"))

    # Missing symbol
    assert any("symbol" in err for err in validate_password_rules("NoSymbolsHere123"))

    # Same as current
    assert any(
        "current password" in err
        for err in validate_password_rules("SamePassword123!", current_password="SamePassword123!")
    )

    # Contains email username
    assert any(
        "username or email" in err
        for err in validate_password_rules("MySecretalice123!", email="alice@example.com")
    )

    # Repetitive characters
    assert any("repetitive" in err for err in validate_password_rules("AaaaaaPassword123!"))


def test_validate_password_rules_accepts_strong_password() -> None:
    errors = validate_password_rules(
        "Correct-Horse-Battery-Staple-2026!",
        current_password="PreviousPassword123!",
        email="bob@example.com",
    )
    assert errors == []


def test_hash_sha512_crypt_generates_valid_format() -> None:
    hashed = hash_sha512_crypt("TestPassword!2026", rounds=5000, salt="saltsaltsaltsalt")
    assert hashed.startswith("{SHA512-CRYPT}$6$rounds=5000$saltsaltsaltsalt$")
    assert len(hashed) > 50


def test_update_accounts_file_password(tmp_path: Any) -> None:
    accounts_file = str(tmp_path / "postfix-accounts.cf")
    with open(accounts_file, "w", encoding="utf-8") as f:
        f.write("user1@example.test|{SHA512-CRYPT}$6$oldhash\n")
        f.write("# comment line\n")
        f.write("user2@example.test|{SHA512-CRYPT}$6$otherhash|extra_field\n")

    update_accounts_file_password(accounts_file, "user1@example.test", "NewPass!2026Safe")

    with open(accounts_file, encoding="utf-8") as f:
        content = f.read()

    assert "user1@example.test|{SHA512-CRYPT}$6$" in content
    assert "oldhash" not in content
    assert "user2@example.test|{SHA512-CRYPT}$6$otherhash|extra_field" in content
    assert "# comment line" in content


def test_change_account_password_verifies_current_and_rotates_session(
    rf: RequestFactory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    accounts_file = str(tmp_path / "accounts.cf")
    with open(accounts_file, "w", encoding="utf-8") as f:
        f.write("demo@example.test|{SHA512-CRYPT}$6$old\n")

    monkeypatch.setattr(
        "apps.accounts.services.password.settings.MAIL_ACCOUNTS_FILE", accounts_file
    )

    request: Any = rf.get("/")
    request.session = SessionStore()
    request.session.save()
    account = MailAccount(
        email="demo@example.test",
        domain="example.test",
        imap_host="imap.example.test",
        imap_port=993,
        imap_security="ssl",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_security="starttls",
    )
    start_mail_session(request, account, "OldPassword!2026")

    # Reject incorrect current password
    with pytest.raises(PasswordValidationError):
        change_account_password(request, "WrongPassword", "NewStrongPassword!2026")

    # Reject weak new password
    with pytest.raises(PasswordValidationError):
        change_account_password(request, "OldPassword!2026", "short")

    # Reject when no backend driver is configured
    monkeypatch.setattr("apps.accounts.services.password.settings.MAIL_ACCOUNTS_FILE", "")
    with pytest.raises(PasswordChangeError):
        change_account_password(request, "OldPassword!2026", "NewStrongPassword!2026")

    # Restore accounts file and succeed with strong new password
    monkeypatch.setattr(
        "apps.accounts.services.password.settings.MAIL_ACCOUNTS_FILE", accounts_file
    )
    change_account_password(request, "OldPassword!2026", "NewStrongPassword!2026")

    # Verify session credential rotated
    new_session_key = request.session.session_key
    assert CredentialStore().load(new_session_key) == "NewStrongPassword!2026"

    # Verify accounts file updated
    with open(accounts_file, encoding="utf-8") as f:
        updated_content = f.read()
    assert "demo@example.test|{SHA512-CRYPT}$6$" in updated_content
