"""Domain exceptions for compose attachments and drafts."""

from __future__ import annotations


class ComposeStateError(Exception):
    """Base class for compose-state failures."""


class EmptyAttachmentError(ComposeStateError):
    """The uploaded file has no content."""


class AttachmentTooLargeError(ComposeStateError):
    """One uploaded file exceeds the per-file limit."""


class AttachmentLimitReachedError(ComposeStateError):
    """The attachment count or total size limit was reached."""
