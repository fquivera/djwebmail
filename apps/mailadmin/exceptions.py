"""Exceptions for mail administration and account driver operations."""

from __future__ import annotations


class MailAdminError(Exception):
    """Base exception for mail administration failures."""


class MailAccountAlreadyExistsError(MailAdminError):
    """Raised when attempting to create a mailbox that already exists."""


class MailAccountNotFoundError(MailAdminError):
    """Raised when an operation targets a mailbox that does not exist."""
