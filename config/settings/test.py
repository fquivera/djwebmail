"""Settings for the automated test suite.

Fast password hashing and no external services by default. Functional tests
that use a real IMAP/SMTP server are opt-in.
"""

from cryptography.fernet import Fernet

from .base import *  # noqa: F403
from .base import env

DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
FERNET_KEY = Fernet.generate_key().decode()
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "djwebmail-tests",
    }
}

# Functional tests use a disposable IMAP/SMTP server. They stay disabled unless
# explicitly enabled, so a normal `pytest` run never contacts a real mailbox.
FUNCTIONAL_TESTS_ENABLED = env.bool("FUNCTIONAL_TESTS_ENABLED", default=False)
FUNCTIONAL_MAIL_USER = env.str("FUNCTIONAL_MAIL_USER", default="demo@example.test")
FUNCTIONAL_MAIL_PASSWORD = env.str("FUNCTIONAL_MAIL_PASSWORD", default="demo")
