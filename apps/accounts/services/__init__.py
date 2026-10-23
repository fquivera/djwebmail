"""Services for IMAP account resolution and protocol operations."""

from apps.accounts.services.account import MailAccount, account_key, resolve_mail_account
from apps.accounts.services.imap import (
    FetchedMessage,
    FetchedSummary,
    Folder,
    FolderStatus,
    ImapService,
)

__all__ = [
    "FetchedMessage",
    "FetchedSummary",
    "Folder",
    "FolderStatus",
    "ImapService",
    "MailAccount",
    "account_key",
    "resolve_mail_account",
]
