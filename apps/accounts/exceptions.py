"""Domain exceptions for IMAP authentication and account resolution."""


class MailError(Exception):
    """Base class for mail-domain failures."""


class MailConfigurationError(MailError):
    """Deployment configuration is missing or invalid."""


class MailAddressError(MailError):
    """The supplied email address is not valid."""


class MailDomainError(MailError):
    """The email address does not belong to the configured mail domain."""


class ImapError(MailError):
    """Base class for IMAP failures."""


class ImapAuthError(ImapError):
    """The IMAP server rejected the credentials."""


class ImapConnectionError(ImapError):
    """The IMAP server could not be reached."""


class ImapProtocolError(ImapError):
    """The IMAP server returned an unexpected or failed response."""


class SmtpError(MailError):
    """Base class for SMTP failures."""


class SmtpAuthError(SmtpError):
    """The SMTP server rejected the credentials."""


class SmtpConnectionError(SmtpError):
    """The SMTP server could not be reached or refused the TLS handshake."""


class SmtpSendError(SmtpError):
    """The SMTP server rejected the message or the recipient list."""


class MailSessionError(MailError):
    """The server-side mail session is missing or no longer usable."""


class PasswordChangeError(MailError):
    """Failure changing an account's email password."""


class PasswordValidationError(MailError):
    """The proposed password violates security policy rules."""
