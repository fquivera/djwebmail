#!/usr/bin/env python3
"""Fail CI when deployment or domain values are hardcoded in source.

Deployment values belong in ``config/settings`` (environment variables),
user choices in the preferences app, and stable domain values in a
``constants.py`` module. This scan catches the common regressions:

- reading ``os.environ`` outside the settings package
- absolute URLs and well-known mail/HTTP ports in application code
- ``localhost``/loopback addresses outside settings and tests
- absolute filesystem paths
- ``print()`` calls instead of the logging configuration
- hardcoded absolute paths in template URL attributes

Suppress a specific line with a reason:

    timeout = 30  # hardcode-ok: protocol-defined default, documented in RFC

    {# hardcode-ok: legacy anchor kept for bookmarked URLs #}

Usage: ``python3 scripts/check_hardcoding.py``
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_DIR = ROOT / "config" / "settings"
SKIP_DIRS = {
    ".git",
    ".venv",
    ".agents",
    "__pycache__",
    "build",
    "dist",
    "docs",
    "media",
    "node_modules",
    "staticfiles",
}
SCAN_ROOTS = ("apps", "common", "config", "templates", "manage.py")
SKIP_RULES_IN_SETTINGS = {"env-access", "url-literal", "port-literal", "localhost-literal"}
PORTS = {25, 110, 143, 465, 587, 993, 995, 8000, 8080}
ENV_ALLOWED = {"manage.py", "config/asgi.py", "config/wsgi.py"}
URL_RE = re.compile(r"https?://")
LOCALHOST_RE = re.compile(r"\b(?:localhost|127\.0\.0\.1|\[::1\])\b")
ABSOLUTE_PATH_RE = re.compile(r"^/(?:home|tmp|var|etc|opt|srv|root)/")
TEMPLATE_URL_RE = re.compile(r'\b(?:href|src|action|hx-(?:get|post|put|patch|delete))="(/[^"{]*)')
TEMPLATE_MARKER = "{# hardcode-ok:"
PYTHON_MARKER = "# hardcode-ok:"

Finding = tuple[Path, int, str, str]


def iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in {".py", ".html"}:
            files.append(path)
    return files


def is_allowed(path: Path, rule: str) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in {"tests", "scripts", "docs", ".agents"} for part in relative.parts):
        return True
    if "migrations" in relative.parts:
        return True
    if rule == "env-access" and relative.as_posix() in ENV_ALLOWED:
        return True
    return SETTINGS_DIR in path.parents and rule in SKIP_RULES_IN_SETTINGS


def line_has_marker(lines: list[str], lineno: int, marker: str) -> bool:
    if 1 <= lineno <= len(lines):
        return marker in lines[lineno - 1]
    return False


def scan_python(path: Path) -> list[Finding]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [(path, exc.lineno or 1, "syntax-error", exc.msg)]

    findings: list[Finding] = []
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))

    def add(node: ast.AST, rule: str, message: str) -> None:
        lineno = getattr(node, "lineno", 1)
        if not line_has_marker(lines, lineno, PYTHON_MARKER) and not is_allowed(path, rule):
            findings.append((path, lineno, rule, message))

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "os"
                and node.attr == "environ"
            ):
                add(node, "env-access", "read environment variables in config/settings only")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "print":
                add(node, "print-call", "use logging instead of print()")
            if isinstance(func, ast.Attribute) and func.attr == "getenv":
                add(node, "env-access", "read environment variables in config/settings only")
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name in {"environ", "getenv"}:
                    add(node, "env-access", "read environment variables in config/settings only")
        elif isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, str) and id(node) not in docstrings:
                if URL_RE.search(value):
                    add(node, "url-literal", f"absolute URL in code: {value!r}")
                if LOCALHOST_RE.search(value):
                    add(node, "localhost-literal", f"loopback host in code: {value!r}")
                if ABSOLUTE_PATH_RE.search(value):
                    add(node, "absolute-path", f"absolute filesystem path: {value!r}")
            elif isinstance(value, int) and not isinstance(value, bool) and value in PORTS:
                add(node, "port-literal", f"well-known port literal: {value}")

    return findings


def scan_template(path: Path) -> list[Finding]:
    lines = path.read_text(encoding="utf-8").splitlines()
    findings: list[Finding] = []
    for lineno, line in enumerate(lines, start=1):
        if TEMPLATE_MARKER in line:
            continue
        match = TEMPLATE_URL_RE.search(line)
        if match:
            findings.append(
                (path, lineno, "template-url", f"use {{% url %}} instead of {match.group(1)!r}")
            )
        if URL_RE.search(line) and "hardcode-ok:" not in line:
            findings.append(
                (
                    path,
                    lineno,
                    "template-url-literal",
                    "serve external assets locally or document an exception",
                )
            )
    return findings


def main() -> int:
    findings: list[Finding] = []
    for name in SCAN_ROOTS:
        for path in iter_files(ROOT / name):
            if path.suffix == ".py":
                findings.extend(scan_python(path))
            else:
                findings.extend(scan_template(path))

    findings.sort(key=lambda item: (str(item[0]), item[1], item[2]))
    for path, lineno, rule, message in findings:
        relative = path.relative_to(ROOT)
        print(f"{relative}:{lineno}: {rule}: {message}")

    if findings:
        print(f"\n{len(findings)} hardcoding issue(s) found.")
        print("Move the value to settings/constants, or add `# hardcode-ok: <reason>`.")
        return 1

    print("No hardcoded configuration detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
