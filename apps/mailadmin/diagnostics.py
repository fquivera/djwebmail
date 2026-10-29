"""Server diagnostics, latency probing, and health inspection for mail services."""

from __future__ import annotations

import datetime
import platform
import re
import socket
import ssl
import time
from dataclasses import dataclass, field
from typing import Any

import django
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.utils.translation import gettext as _

from apps.mailadmin.constants import (
    DEFAULT_DIAGNOSTIC_HELO_DOMAIN,
    DEFAULT_DIAGNOSTIC_TIMEOUT_SECONDS,
)
from apps.mailadmin.drivers.factory import get_account_driver
from common.version import get_djwebmail_version


@dataclass(slots=True)
class ServiceCheckResult:
    """Normalized result of an individual service connectivity and health check."""

    service_name: str
    endpoint: str
    is_online: bool
    latency_ms: float | None = None
    banner: str = ""
    capabilities: list[str] = field(default_factory=list)
    error_message: str | None = None
    engine_detected: str = ""

    @property
    def latency_display(self) -> str:
        if self.latency_ms is None:
            return "N/A"
        return f"{self.latency_ms:.1f} ms"

    @property
    def status_label(self) -> str:
        if self.is_online:
            return _("Online")
        return _("Offline")


def detect_mail_engine_from_banner(banner: str) -> str:
    """Identify mail server daemon from greeting banner strings."""
    banner_lower = banner.lower()
    if "dovecot" in banner_lower:
        return "Dovecot"
    if "postfix" in banner_lower:
        return "Postfix"
    if "greenmail" in banner_lower:
        return "GreenMail (Test Server)"
    if "courier" in banner_lower:
        return "Courier"
    if "exim" in banner_lower:
        return "Exim"
    if "cyrus" in banner_lower:
        return "Cyrus IMAP"
    if "gmail" in banner_lower or "google" in banner_lower:
        return "Google Workspace / Gmail"
    return ""


def check_imap_service(
    host: str | None = None,
    port: int | None = None,
    security: str | None = None,
    verify_tls: bool | None = None,
    timeout: int = DEFAULT_DIAGNOSTIC_TIMEOUT_SECONDS,
) -> ServiceCheckResult:
    """Probe IMAP service connectivity, measure latency, and discover capabilities."""
    default_imap_port = 993  # hardcode-ok: default IMAP protocol port
    target_host = host if host is not None else getattr(settings, "MAIL_IMAP_HOST", "")
    target_port = (
        port if port is not None else getattr(settings, "MAIL_IMAP_PORT", default_imap_port)
    )
    sec_setting = getattr(settings, "MAIL_IMAP_SECURITY", "ssl")
    target_sec = (security if security is not None else sec_setting).lower()
    target_verify = (
        verify_tls if verify_tls is not None else getattr(settings, "MAIL_VERIFY_TLS", True)
    )

    endpoint_desc = f"{target_host}:{target_port} ({target_sec.upper()})"
    if not target_host:
        return ServiceCheckResult(
            service_name="IMAP",
            endpoint=endpoint_desc,
            is_online=False,
            error_message=_("IMAP host is not configured in settings."),
        )

    start = time.perf_counter()
    sock: socket.socket | ssl.SSLSocket | None = None
    try:
        raw_sock = socket.create_connection((target_host, target_port), timeout=timeout)
        if target_sec == "ssl":
            ctx = ssl.create_default_context()
            if not target_verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(raw_sock, server_hostname=target_host)
        else:
            sock = raw_sock

        reader = sock.makefile("r", encoding="utf-8", errors="replace")
        writer = sock.makefile("w", encoding="utf-8", errors="replace")

        # Read IMAP Greeting
        banner = reader.readline().strip()
        latency = (time.perf_counter() - start) * 1000

        capabilities: list[str] = []
        # Parse capabilities from greeting if embedded: * OK [CAPABILITY ...]
        cap_match = re.search(r"\[CAPABILITY ([^\]]+)\]", banner, re.IGNORECASE)
        if cap_match:
            capabilities = cap_match.group(1).split()

        # Query explicit CAPABILITY if not in greeting
        if not capabilities and banner.startswith("*"):
            try:
                writer.write("A001 CAPABILITY\r\n")
                writer.flush()
                while True:
                    line = reader.readline()
                    if not line:
                        break
                    line_clean = line.strip()
                    if line_clean.startswith("* CAPABILITY"):
                        capabilities = line_clean.replace("* CAPABILITY", "").strip().split()
                    if line_clean.startswith("A001 "):
                        break
            except OSError:
                pass

        # Clean logout
        try:
            writer.write("A002 LOGOUT\r\n")
            writer.flush()
        except OSError:
            pass

        engine = detect_mail_engine_from_banner(banner)
        return ServiceCheckResult(
            service_name="IMAP",
            endpoint=endpoint_desc,
            is_online=True,
            latency_ms=latency,
            banner=banner,
            capabilities=capabilities,
            engine_detected=engine,
        )
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return ServiceCheckResult(
            service_name="IMAP",
            endpoint=endpoint_desc,
            is_online=False,
            latency_ms=latency,
            error_message=str(exc),
        )
    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass


def check_smtp_service(
    host: str | None = None,
    port: int | None = None,
    security: str | None = None,
    verify_tls: bool | None = None,
    timeout: int = DEFAULT_DIAGNOSTIC_TIMEOUT_SECONDS,
) -> ServiceCheckResult:
    """Probe SMTP service connectivity, measure latency, and discover advertised extensions."""
    default_smtp_port = 587  # hardcode-ok: default SMTP submission port
    target_host = host if host is not None else getattr(settings, "MAIL_SMTP_HOST", "")
    target_port = (
        port if port is not None else getattr(settings, "MAIL_SMTP_PORT", default_smtp_port)
    )
    sec_setting = getattr(settings, "MAIL_SMTP_SECURITY", "starttls")
    target_sec = (security if security is not None else sec_setting).lower()
    target_verify = (
        verify_tls if verify_tls is not None else getattr(settings, "MAIL_VERIFY_TLS", True)
    )

    endpoint_desc = f"{target_host}:{target_port} ({target_sec.upper()})"
    if not target_host:
        return ServiceCheckResult(
            service_name="SMTP",
            endpoint=endpoint_desc,
            is_online=False,
            error_message=_("SMTP host is not configured in settings."),
        )

    start = time.perf_counter()
    sock: socket.socket | ssl.SSLSocket | None = None
    try:
        raw_sock = socket.create_connection((target_host, target_port), timeout=timeout)
        if target_sec == "ssl":
            ctx = ssl.create_default_context()
            if not target_verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(raw_sock, server_hostname=target_host)
        else:
            sock = raw_sock

        reader = sock.makefile("r", encoding="utf-8", errors="replace")
        writer = sock.makefile("w", encoding="utf-8", errors="replace")

        # Read SMTP Greeting (220)
        banner = reader.readline().strip()
        latency = (time.perf_counter() - start) * 1000

        capabilities: list[str] = []
        # Send EHLO
        domain_name = getattr(settings, "MAIL_DOMAIN", "") or DEFAULT_DIAGNOSTIC_HELO_DOMAIN
        writer.write(f"EHLO {domain_name}\r\n")
        writer.flush()

        while True:
            line = reader.readline()
            if not line:
                break
            line_clean = line.strip()
            # 250-STARTTLS or 250 OK
            if line_clean.startswith("250"):
                cap_part = line_clean[4:].strip()
                if cap_part:
                    capabilities.append(cap_part)
                if line_clean.startswith("250 "):
                    break
            elif not line_clean.startswith("2"):
                break

        # Send QUIT
        try:
            writer.write("QUIT\r\n")
            writer.flush()
        except OSError:
            pass

        engine = detect_mail_engine_from_banner(banner)
        return ServiceCheckResult(
            service_name="SMTP",
            endpoint=endpoint_desc,
            is_online=True,
            latency_ms=latency,
            banner=banner,
            capabilities=capabilities,
            engine_detected=engine,
        )
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return ServiceCheckResult(
            service_name="SMTP",
            endpoint=endpoint_desc,
            is_online=False,
            latency_ms=latency,
            error_message=str(exc),
        )
    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass


def check_database_service() -> ServiceCheckResult:
    """Execute a query against the active database and measure round-trip latency."""
    vendor = connection.vendor.capitalize()
    engine_name = connection.settings_dict.get("ENGINE", "").split(".")[-1]
    name = connection.settings_dict.get("NAME", "")
    endpoint_desc = f"{vendor} ({engine_name}: {name})"

    start = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        latency = (time.perf_counter() - start) * 1000
        return ServiceCheckResult(
            service_name=_("Database"),
            endpoint=endpoint_desc,
            is_online=True,
            latency_ms=latency,
            engine_detected=vendor,
        )
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return ServiceCheckResult(
            service_name=_("Database"),
            endpoint=endpoint_desc,
            is_online=False,
            latency_ms=latency,
            error_message=str(exc),
        )


def check_cache_service() -> ServiceCheckResult:
    """Check cache set/get connectivity and measure round-trip latency."""
    cache_backend = settings.CACHES["default"]["BACKEND"].split(".")[-1]
    endpoint_desc = f"{cache_backend}"

    test_key = "__diag_ping__"
    start = time.perf_counter()
    try:
        cache.set(test_key, 1, timeout=10)
        val = cache.get(test_key)
        cache.delete(test_key)
        latency = (time.perf_counter() - start) * 1000
        if val != 1:
            return ServiceCheckResult(
                service_name=_("Cache & Sessions"),
                endpoint=endpoint_desc,
                is_online=False,
                latency_ms=latency,
                error_message=_("Cache read-back mismatch."),
            )
        return ServiceCheckResult(
            service_name=_("Cache & Sessions"),
            endpoint=endpoint_desc,
            is_online=True,
            latency_ms=latency,
            engine_detected=cache_backend,
        )
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return ServiceCheckResult(
            service_name=_("Cache & Sessions"),
            endpoint=endpoint_desc,
            is_online=False,
            latency_ms=latency,
            error_message=str(exc),
        )


def get_system_diagnostics() -> dict[str, Any]:
    """Gather diagnostic runtime metadata about Python, Django, environment, and security."""
    driver = get_account_driver()
    return {
        "python_version": platform.python_version(),
        "django_version": django.get_version(),
        "djwebmail_version": get_djwebmail_version(),
        "os_platform": f"{platform.system()} {platform.release()}",
        "driver_class": driver.__class__.__name__,
        "debug_mode": settings.DEBUG,
        "fernet_configured": bool(getattr(settings, "FERNET_KEY", "")),
        "session_cookie_age": settings.SESSION_COOKIE_AGE,
        "session_cookie_secure": settings.SESSION_COOKIE_SECURE,
        "session_cookie_httponly": settings.SESSION_COOKIE_HTTPONLY,
        "csrf_cookie_secure": settings.CSRF_COOKIE_SECURE,
        "mail_domain": getattr(settings, "MAIL_DOMAIN", "") or _("Not configured"),
    }


def run_full_diagnostics() -> dict[str, Any]:
    """Execute all diagnostic probes and return an aggregated health report."""
    imap_result = check_imap_service()
    smtp_result = check_smtp_service()
    db_result = check_database_service()
    cache_result = check_cache_service()
    system_info = get_system_diagnostics()

    all_online = all(
        [imap_result.is_online, smtp_result.is_online, db_result.is_online, cache_result.is_online]
    )
    core_online = db_result.is_online and cache_result.is_online

    if all_online:
        overall_status = "healthy"
        overall_label = _("All systems operational")
    elif core_online:
        overall_status = "degraded"
        overall_label = _("Degraded connectivity")
    else:
        overall_status = "unhealthy"
        overall_label = _("System issues detected")

    return {
        "imap": imap_result,
        "smtp": smtp_result,
        "database": db_result,
        "cache": cache_result,
        "system": system_info,
        "overall_status": overall_status,
        "overall_label": overall_label,
        "checked_at": datetime.datetime.now(),
    }
