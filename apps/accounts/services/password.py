"""Password validation, hashing, and email account backend update drivers."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import re
import secrets
import socket
import string
import tempfile
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils.translation import gettext as _

from apps.accounts.constants import (
    DEFAULT_POPPASSD_PORT,
    PASSWORD_MAX_REPEATED_CHARS,
    PASSWORD_MIN_LENGTH,
)
from apps.accounts.exceptions import (
    PasswordChangeError,
    PasswordValidationError,
)
from apps.accounts.services.session import _mail_credentials, update_mail_session_password

if TYPE_CHECKING:
    from django.http import HttpRequest

_SPECIAL_CHARS_RE = re.compile(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]")
_REPEATED_CHARS_RE = re.compile(rf"(.)\1{{{PASSWORD_MAX_REPEATED_CHARS - 1},}}")


def validate_password_rules(
    new_password: str,
    *,
    current_password: str = "",
    email: str = "",
) -> list[str]:
    """Validate minimum security rules according to OWASP ASVS and NIST guidelines."""
    errors: list[str] = []

    if len(new_password) < PASSWORD_MIN_LENGTH:
        errors.append(
            _("The new password must be at least %(min)d characters long.")
            % {"min": PASSWORD_MIN_LENGTH}
        )

    if not re.search(r"[A-Z]", new_password):
        errors.append(_("The new password must contain at least one uppercase letter."))

    if not re.search(r"[a-z]", new_password):
        errors.append(_("The new password must contain at least one lowercase letter."))

    if not re.search(r"[0-9]", new_password):
        errors.append(_("The new password must contain at least one number."))

    if not _SPECIAL_CHARS_RE.search(new_password):
        errors.append(_("The new password must contain at least one special symbol."))

    if current_password and new_password == current_password:
        errors.append(_("The new password cannot be the same as your current password."))

    if email:
        email_lower = email.strip().lower()
        user_part = email_lower.split("@")[0]
        if user_part and len(user_part) >= 3 and user_part in new_password.lower():
            errors.append(_("The new password cannot contain your username or email."))

    if _REPEATED_CHARS_RE.search(new_password):
        errors.append(_("The new password cannot contain repetitive sequences of characters."))

    return errors


def hash_sha512_crypt(password: str, rounds: int = 5000, salt: str | None = None) -> str:
    """Generate a {SHA512-CRYPT} hash compatible with Dovecot and docker-mailserver."""
    lib_path = ctypes.util.find_library("crypt")
    if not lib_path:
        raise PasswordChangeError(_("System cryptographic library (libcrypt) is not available."))

    lib = ctypes.CDLL(lib_path)
    if not hasattr(lib, "crypt"):
        raise PasswordChangeError(_("System libcrypt does not provide the crypt function."))

    lib.crypt.restype = ctypes.c_char_p
    lib.crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]

    if not salt:
        alphabet = string.ascii_letters + string.digits
        salt = "".join(secrets.choice(alphabet) for _ in range(16))

    setting = f"$6$rounds={rounds}${salt}$".encode("ascii")
    hashed = lib.crypt(password.encode("utf-8"), setting)
    if not hashed:
        raise PasswordChangeError(_("Failed to generate password hash."))

    return "{SHA512-CRYPT}" + hashed.decode("ascii")


def update_accounts_file_password(accounts_file: str, email: str, new_password: str) -> None:
    """Update or append an account's SHA512-CRYPT entry in postfix-accounts.cf atomically."""
    target_email = email.strip().lower()
    if not os.path.isfile(accounts_file):
        raise PasswordChangeError(
            _("Accounts file '%(path)s' does not exist.") % {"path": accounts_file}
        )

    hashed_password = hash_sha512_crypt(new_password)
    lines: list[str] = []
    found = False

    try:
        with open(accounts_file, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.rstrip("\r\n")
                if not line or line.startswith("#"):
                    lines.append(line)
                    continue

                parts = line.split("|")
                if parts and parts[0].strip().lower() == target_email:
                    # preserve any extra fields (e.g. maildir, quota)
                    rest = parts[2:] if len(parts) > 2 else []
                    new_line = "|".join([parts[0], hashed_password, *rest])
                    lines.append(new_line)
                    found = True
                else:
                    lines.append(line)

        if not found:
            lines.append(f"{target_email}|{hashed_password}")

        file_dir = os.path.dirname(os.path.abspath(accounts_file))
        with tempfile.NamedTemporaryFile("w", dir=file_dir, encoding="utf-8", delete=False) as tmp:
            tmp.write("\n".join(lines) + "\n")
            tmp_path = tmp.name

        os.replace(tmp_path, accounts_file)
    except OSError as exc:
        raise PasswordChangeError(
            _("Failed to update accounts file: %(error)s") % {"error": str(exc)}
        ) from exc


def update_poppassd_password(
    host: str,
    port: int,
    email: str,
    current_password: str,
    new_password: str,
    timeout: int = 30,
) -> None:
    """Execute a password change over the POPPASSD protocol (port 106)."""
    user = email.split("@")[0]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)

    try:
        sock.connect((host, port or DEFAULT_POPPASSD_PORT))
        reader = sock.makefile("r", encoding="utf-8", errors="replace")
        writer = sock.makefile("w", encoding="utf-8", errors="replace")

        # Greeting
        greeting = reader.readline()
        if not greeting or not greeting.startswith(("2", "3")):
            raise PasswordChangeError(
                _("POPPASSD server rejected connection: %(msg)s") % {"msg": greeting.strip()}
            )

        # USER
        writer.write(f"USER {user}\r\n")
        writer.flush()
        user_res = reader.readline()
        if not user_res or not user_res.startswith(("2", "3")):
            raise PasswordChangeError(
                _("POPPASSD rejected user: %(msg)s") % {"msg": user_res.strip()}
            )

        # PASS
        writer.write(f"PASS {current_password}\r\n")
        writer.flush()
        pass_res = reader.readline()
        if not pass_res or not pass_res.startswith(("2", "3")):
            raise PasswordChangeError(
                _("POPPASSD rejected current password: %(msg)s") % {"msg": pass_res.strip()}
            )

        # NEWPASS
        writer.write(f"NEWPASS {new_password}\r\n")
        writer.flush()
        newpass_res = reader.readline()
        if not newpass_res or not newpass_res.startswith(("2", "3")):
            raise PasswordChangeError(
                _("POPPASSD rejected new password: %(msg)s") % {"msg": newpass_res.strip()}
            )

        # QUIT
        writer.write("QUIT\r\n")
        writer.flush()
    except OSError as exc:
        raise PasswordChangeError(
            _("Could not reach POPPASSD server: %(error)s") % {"error": str(exc)}
        ) from exc
    finally:
        sock.close()


def is_password_change_configured() -> bool:
    """Return True if password change is enabled and at least one backend driver is configured."""
    if not getattr(settings, "MAIL_CHANGE_PASSWORD_ENABLED", True):
        return False
    return bool(
        getattr(settings, "MAIL_ACCOUNTS_FILE", "") or getattr(settings, "MAIL_POPPASSD_HOST", "")
    )


def change_account_password(
    request: HttpRequest,
    current_password: str,
    new_password: str,
) -> None:
    """Verify current credentials, validate security rules, update backend, and rotate session."""
    if not settings.MAIL_CHANGE_PASSWORD_ENABLED:
        raise PasswordChangeError(_("Password change is not enabled for this server."))

    accounts_file = getattr(settings, "MAIL_ACCOUNTS_FILE", "")
    poppassd_host = getattr(settings, "MAIL_POPPASSD_HOST", "")

    if not accounts_file and not poppassd_host:
        raise PasswordChangeError(
            _(
                "No password backend driver is configured for this deployment. "
                "Please configure DJANGO_MAIL_ACCOUNTS_FILE or DJANGO_MAIL_POPPASSD_HOST."
            )
        )

    account, cached_password = _mail_credentials(request)

    if current_password != cached_password:
        raise PasswordValidationError(_("The current password is incorrect."))

    errors = validate_password_rules(
        new_password,
        current_password=current_password,
        email=account.email,
    )
    if errors:
        raise PasswordValidationError(errors[0])

    if accounts_file:
        update_accounts_file_password(accounts_file, account.email, new_password)
    elif poppassd_host:
        poppassd_port = getattr(settings, "MAIL_POPPASSD_PORT", DEFAULT_POPPASSD_PORT)
        timeout = getattr(settings, "MAIL_TIMEOUT_SECONDS", 30)
        update_poppassd_password(
            poppassd_host,
            poppassd_port,
            account.email,
            current_password,
            new_password,
            timeout=timeout,
        )

    # Rotate the session credential with the new password
    update_mail_session_password(request, new_password)
