"""Base settings shared by every environment.

Environment modules (``development``, ``test``, ``production``) import from
this module and override only what differs.
"""

from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env.str("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = [
    host.strip() for host in env.str("DJANGO_ALLOWED_HOSTS", default="").split(",") if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tailwind",
    "theme",
    "apps.accounts",
    "apps.mail",
    "apps.compose",
    "apps.preferences",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.MailSessionMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASE_URL = env.str("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")
DATABASES = {"default": env.db_url_config(DATABASE_URL)}

REDIS_URL = env.str("REDIS_URL", default="")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "djwebmail",
        }
    }

FERNET_KEY = env.str("FERNET_KEY", default="")
SESSION_COOKIE_AGE = env.int("DJANGO_SESSION_COOKIE_AGE", default=28800)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = env.str("DJANGO_LANGUAGE_CODE", default="en-us")
LANGUAGES = [
    ("en", _("English")),
    ("es", _("Spanish")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Tailwind/daisyUI is compiled by `manage.py tailwind build` before collectstatic.
# The standalone CLI keeps Node and npm out of production and CI.
TAILWIND_APP_NAME = "theme"
TAILWIND_USE_STANDALONE_BINARY = True
TAILWIND_STANDALONE_BINARY_VERSION = "v4.3.3"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# IMAP/SMTP defaults consumed by apps.accounts services. Users can override
# them from the UI later; empty values mean "not configured yet".
MAIL_IMAP_HOST = env.str("DJANGO_MAIL_IMAP_HOST", default="")
MAIL_IMAP_PORT = env.int("DJANGO_MAIL_IMAP_PORT", default=993)
MAIL_IMAP_SECURITY = env.str("DJANGO_MAIL_IMAP_SECURITY", default="ssl")
MAIL_VERIFY_TLS = env.bool("DJANGO_MAIL_VERIFY_TLS", default=True)
MAIL_TIMEOUT_SECONDS = env.int("DJANGO_MAIL_TIMEOUT_SECONDS", default=30)
MAIL_DEFAULT_PAGE_SIZE = env.int("DJANGO_MAIL_DEFAULT_PAGE_SIZE", default=50)
MAIL_MAX_PAGE_SIZE = env.int("DJANGO_MAIL_MAX_PAGE_SIZE", default=200)
MAIL_DOMAIN = env.str("DJANGO_MAIL_DOMAIN", default="")
MAIL_SMTP_HOST = env.str("DJANGO_MAIL_SMTP_HOST", default="")
MAIL_SMTP_PORT = env.int("DJANGO_MAIL_SMTP_PORT", default=587)
MAIL_SMTP_SECURITY = env.str("DJANGO_MAIL_SMTP_SECURITY", default="starttls")
MAIL_LOGIN_MAX_ATTEMPTS = env.int("DJANGO_MAIL_LOGIN_MAX_ATTEMPTS", default=5)
MAIL_LOGIN_WINDOW_SECONDS = env.int("DJANGO_MAIL_LOGIN_WINDOW_SECONDS", default=300)
MAIL_IMAGE_PROXY_MAX_BYTES = env.int("DJANGO_MAIL_IMAGE_PROXY_MAX_BYTES", default=5_000_000)
MAIL_IMAGE_PROXY_TIMEOUT_SECONDS = env.int("DJANGO_MAIL_IMAGE_PROXY_TIMEOUT_SECONDS", default=10)

if SESSION_COOKIE_AGE <= 0:
    raise ImproperlyConfigured("DJANGO_SESSION_COOKIE_AGE must be positive")
if MAIL_LOGIN_MAX_ATTEMPTS <= 0:
    raise ImproperlyConfigured("DJANGO_MAIL_LOGIN_MAX_ATTEMPTS must be positive")
if MAIL_LOGIN_WINDOW_SECONDS <= 0:
    raise ImproperlyConfigured("DJANGO_MAIL_LOGIN_WINDOW_SECONDS must be positive")
if MAIL_IMAGE_PROXY_MAX_BYTES <= 0:
    raise ImproperlyConfigured("DJANGO_MAIL_IMAGE_PROXY_MAX_BYTES must be positive")
if MAIL_IMAGE_PROXY_TIMEOUT_SECONDS <= 0:
    raise ImproperlyConfigured("DJANGO_MAIL_IMAGE_PROXY_TIMEOUT_SECONDS must be positive")

X_FRAME_OPTIONS = "DENY"

# Strict CSP for the webmail: no `unsafe-eval`/`unsafe-inline`, no third-party
# origins, and no framing. HTMX runs with `allowEval=false` and
# `allowScriptTags=false`; daisyUI theme styles and HTMX indicator styles live
# in the compiled stylesheet instead of inline `<style>` blocks.
#
# Django admin injects inline scripts/styles, so it is excluded from the
# webmail policy (it keeps X-Frame-Options: DENY). The debug toolbar is excluded
# for the same reason in development.
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "base-uri": ["'self'"],
        "object-src": ["'none'"],
        "frame-ancestors": ["'none'"],
        "form-action": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'"],
        "img-src": ["'self'", "data:", "blob:"],
        "font-src": ["'self'"],
        "connect-src": ["'self'"],
        "media-src": ["'self'"],
    },
    "EXCLUDE_URL_PREFIXES": ("/admin/", "/__debug__/"),
}

SECURE_CONTENT_TYPE_NOSNIFF = True
# ``no-referrer`` makes Chromium 156+ send ``Origin: null`` on same-origin form
# POSTs, which breaks CSRF origin validation. ``same-origin`` keeps the
# referrer out of cross-origin requests without breaking same-origin forms.
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {"format": "%(levelname)s %(asctime)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "console"},
    },
    "root": {"handlers": ["console"], "level": env.str("DJANGO_LOG_LEVEL", default="INFO")},
}
