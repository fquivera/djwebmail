"""Production settings.

Assumes HTTPS terminated by a reverse proxy and WhiteNoise serving static
assets. ``ALLOWED_HOSTS`` must be provided by the environment.
"""

from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import ALLOWED_HOSTS, FERNET_KEY, MIDDLEWARE, REDIS_URL, env

DEBUG = False

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production")
if not REDIS_URL:
    raise ImproperlyConfigured("REDIS_URL must be set in production")
if not FERNET_KEY:
    raise ImproperlyConfigured("FERNET_KEY must be set in production")
try:
    Fernet(FERNET_KEY.encode("ascii"))
except (TypeError, ValueError, UnicodeEncodeError) as exc:
    raise ImproperlyConfigured("FERNET_KEY must be a valid Fernet key") from exc

MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in env.str("CSRF_TRUSTED_ORIGINS", default="").split(",")
    if origin.strip()
]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
