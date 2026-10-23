"""Local staging settings.

Reuses the production stack (Gunicorn, WhiteNoise, Redis, fail-fast checks)
but relaxes HTTPS-only cookie and redirect settings so the stack can be
exercised over loopback HTTP. Never expose this stack to the internet.
"""

from .base import env
from .production import *  # noqa: F403

DEBUG = False
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=False)
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
