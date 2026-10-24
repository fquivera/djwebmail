"""Build and send outgoing mail.

The service layer owns RFC 5322 assembly so views only validate input and
choose a response. Nothing here reads or writes the database: the message is
handed to SMTP and (later) appended to the Sent folder over IMAP.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from html import unescape

from django.utils import formats
from django.utils.translation import gettext as _

from apps.accounts.services.smtp import SmtpService
from apps.compose.attachments import Attachment
from apps.compose.constants import (
    MAX_SUBJECT_LENGTH,
    SUBJECT_FORWARD_PREFIX,
    SUBJECT_REPLY_PREFIX,
)
from apps.mail.services.message import MessageDetail

_TAG_PATTERN = re.compile(r"<[^>]+>")
_SPACE_PATTERN = re.compile(r"[ \t\u00a0]+")


def build_message(
    *,
    sender: str,
    to: Sequence[str],
    cc: Sequence[str],
    subject: str,
    body: str,
    attachments: Sequence[Attachment] = (),
) -> EmailMessage:
    """Assemble a plain-text RFC 5322 message with a stable Message-ID."""
    message = EmailMessage()
    message["From"] = sender
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject[:MAX_SUBJECT_LENGTH]
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1])
    message.set_content(body)
    for attachment in attachments:
        _add_attachment(message, attachment)
    return message


def send_message(
    smtp: SmtpService,
    *,
    sender: str,
    to: Sequence[str],
    cc: Sequence[str],
    subject: str,
    body: str,
    attachments: Sequence[Attachment] = (),
) -> None:
    """Build the message and hand it to SMTP for every recipient."""
    message = build_message(
        sender=sender,
        to=to,
        cc=cc,
        subject=subject,
        body=body,
        attachments=attachments,
    )
    smtp.send(sender, [*to, *cc], message.as_bytes())


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
