"""Build and send outgoing mail.

The service layer owns RFC 5322 assembly so views only validate input and
choose a response. Nothing here reads or writes the database: the message is
handed to SMTP and (later) appended to the Sent folder over IMAP.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import formatdate, getaddresses, make_msgid, parseaddr
from html import unescape

from django.utils import formats
from django.utils.translation import gettext as _

from apps.accounts.services.imap import ImapService
from apps.accounts.services.smtp import SmtpService
from apps.compose.attachments import Attachment
from apps.compose.constants import (
    MAX_SUBJECT_LENGTH,
    SUBJECT_FORWARD_PREFIX,
    SUBJECT_REPLY_PREFIX,
)
from apps.mail.constants import FOLDER_FLAG_NOSELECT, MESSAGE_FLAG_SEEN
from apps.mail.services.message import MessageDetail

_DEFAULT_SENT_FOLDER = "Sent"
_SENT_FOLDER_NAMES = frozenset({"sent", "sent messages", "sent items", "enviados"})
_SENT_FOLDER_FLAG = "\\sent"
_TAG_PATTERN = re.compile(r"<[^>]+>")
_SPACE_PATTERN = re.compile(r"[ \t\u00a0]+")
_HTML_TAGS_PATTERN = re.compile(
    r"<(p|div|br|b|i|u|s|ul|ol|li|h[1-6]|span|a|strong|em)\b",
    re.IGNORECASE,
)


def decode_mime_words(value: str) -> str:
    """Decode RFC 2047 encoded-words (``=?utf-8?q?...?=``) into human-readable Unicode."""
    text = value.replace("\r", " ").replace("\n", " ").strip()
    if "=?" not in text:
        return text
    try:
        return str(make_header(decode_header(text))).strip()
    except Exception:
        return text


def format_sender_address(email: str, display_name: str = "") -> str:
    """Format an RFC 5322 From header with an optional owner display name."""
    clean_email = email.strip()
    clean_name = decode_mime_words(display_name).replace('"', "").strip()
    if clean_name and clean_email:
        if any(ch in clean_name for ch in (",", ";", "<", ">")):
            return f'"{clean_name}" <{clean_email}>'
        return f"{clean_name} <{clean_email}>"
    return clean_email


def build_message(
    *,
    sender: str,
    sender_name: str = "",
    to: Sequence[str],
    cc: Sequence[str],
    bcc: Sequence[str] = (),
    subject: str,
    body: str,
    attachments: Sequence[Attachment] = (),
) -> EmailMessage:
    """Assemble an RFC 5322 message with plain-text or HTML alternative and stable Message-ID."""
    _, parsed_email = parseaddr(sender)
    envelope_sender = parsed_email or sender.strip()
    message = EmailMessage()
    message["From"] = format_sender_address(envelope_sender, sender_name) if sender_name else sender
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject[:MAX_SUBJECT_LENGTH]
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=envelope_sender.rsplit("@", 1)[-1])

    # If body contains rich HTML markup, assemble multipart/alternative
    if "<" in body and ">" in body and _HTML_TAGS_PATTERN.search(body):
        plain_text = html_to_text(body)
        message.set_content(plain_text)
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)

    for attachment in attachments:
        _add_attachment(message, attachment)
    return message


def send_message(
    smtp: SmtpService,
    *,
    sender: str,
    sender_name: str = "",
    to: Sequence[str],
    cc: Sequence[str],
    bcc: Sequence[str] = (),
    subject: str,
    body: str,
    attachments: Sequence[Attachment] = (),
) -> bytes:
    """Build the message, hand it to SMTP for every recipient, and return raw bytes."""
    message = build_message(
        sender=sender,
        sender_name=sender_name,
        to=to,
        cc=cc,
        bcc=bcc,
        subject=subject,
        body=body,
        attachments=attachments,
    )
    raw = message.as_bytes()
    _, parsed_email = parseaddr(sender)
    smtp.send(parsed_email or sender, [*to, *cc, *bcc], raw)
    return raw


def append_to_sent(imap: ImapService, raw: bytes) -> bool:
    """Append a sent message to the account's Sent folder when present."""
    if not hasattr(imap, "list_folders") or not hasattr(imap, "append"):
        return False
    folders = imap.list_folders()
    target = ""
    for folder in folders:
        if any(flag.casefold() == FOLDER_FLAG_NOSELECT.casefold() for flag in folder.flags):
            continue
        if any(flag.casefold() == _SENT_FOLDER_FLAG for flag in folder.flags):
            target = folder.name
            break
        leaf = folder.name.rsplit(folder.delimiter, 1)[-1] if folder.delimiter else folder.name
        if leaf.casefold() in _SENT_FOLDER_NAMES or folder.name.casefold() in _SENT_FOLDER_NAMES:
            target = folder.name
    if not target:
        if hasattr(imap, "create_folder"):
            imap.create_folder(_DEFAULT_SENT_FOLDER)
            target = _DEFAULT_SENT_FOLDER
        else:
            return False
    imap.append(target, raw, flags=(MESSAGE_FLAG_SEEN,))
    return True


def apply_signature(initial: dict[str, str], signature: str) -> dict[str, str]:
    """Attach the account signature to the initial compose fields when non-empty."""
    clean_sig = signature.strip()
    if not clean_sig:
        return initial
    updated = dict(initial)
    existing = updated.get("body", "").strip()
    if existing:
        updated["body"] = f"\n\n-- \n{clean_sig}\n\n{existing}"
    else:
        updated["body"] = f"\n\n-- \n{clean_sig}"
    return updated


def _add_attachment(message: EmailMessage, attachment: Attachment) -> None:
    maintype, _, subtype = attachment.content_type.partition("/")
    if not maintype or not subtype:
        maintype, subtype = "application", "octet-stream"
    message.add_attachment(
        attachment.content,
        maintype=maintype,
        subtype=subtype,
        filename=attachment.name,
    )


def reply_initial(message: MessageDetail) -> dict[str, str]:
    """Prefill the form for replying to ``message``."""
    return {
        "to": parseaddr(message.sender)[1],
        "subject": _with_prefix(SUBJECT_REPLY_PREFIX, message.subject),
    }


def reply_all_initial(
    message: MessageDetail,
    account_email: str = "",
) -> dict[str, str]:
    """Prefill the form for replying to all participants of ``message``."""
    own = account_email.strip().casefold()
    sender_addr = parseaddr(message.sender)[1].strip()
    to_list: list[str] = []
    seen: set[str] = set()

    if sender_addr:
        to_list.append(sender_addr)
        seen.add(sender_addr.casefold())

    for _name, addr in getaddresses([message.recipients]):
        clean = addr.strip()
        lowered = clean.casefold()
        if clean and lowered != own and lowered not in seen:
            to_list.append(clean)
            seen.add(lowered)

    cc_list: list[str] = []
    for _name, addr in getaddresses([message.cc]):
        clean = addr.strip()
        lowered = clean.casefold()
        if clean and lowered != own and lowered not in seen:
            cc_list.append(clean)
            seen.add(lowered)

    return {
        "to": ", ".join(to_list),
        "cc": ", ".join(cc_list),
        "subject": _with_prefix(SUBJECT_REPLY_PREFIX, message.subject),
    }


def forward_initial(message: MessageDetail) -> dict[str, str]:
    """Prefill the form for forwarding ``message``."""
    return {
        "subject": _with_prefix(SUBJECT_FORWARD_PREFIX, message.subject),
        "body": _forward_body(message),
    }


def _with_prefix(prefix: str, subject: str) -> str:
    if subject.lower().startswith(prefix.lower()):
        return subject
    return f"{prefix} {subject}".strip()


def _forward_body(message: MessageDetail) -> str:
    date = formats.date_format(message.date, "DATETIME_FORMAT") if message.date else ""
    lines = [
        _("---------- Forwarded message ---------"),
        _("From: %(value)s") % {"value": message.sender},
        _("Date: %(value)s") % {"value": date},
        _("Subject: %(value)s") % {"value": message.subject},
        _("To: %(value)s") % {"value": message.recipients},
        "",
        html_to_text(message.body_html),
    ]
    return "\n".join(lines).strip()


def html_to_text(value: str) -> str:
    """Turn sanitized HTML into a readable plain-text approximation."""
    text = unescape(_TAG_PATTERN.sub(" ", value))
    lines = [_SPACE_PATTERN.sub(" ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
