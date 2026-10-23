"""Services for IMAP account resolution and protocol operations."""

from apps.accounts.services.account import MailAccount, account_key, resolve_mail_account
from apps.accounts.services.imap import FetchedMessage, Folder, FolderStatus, ImapService

__all__ = [
    "FetchedMessage",
    "Folder",
    "FolderStatus",
    "ImapService",
    "MailAccount",
    "account_key",
    "resolve_mail_account",
]
