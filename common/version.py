"""Version discovery for DjWebmail."""

from __future__ import annotations

import functools
import tomllib
from pathlib import Path

from django.conf import settings

from common.constants import DEFAULT_APP_VERSION


@functools.lru_cache(maxsize=1)
def get_djwebmail_version() -> str:
    """Return the installed or source version of DjWebmail."""
    base_dir = getattr(settings, "BASE_DIR", Path.cwd())
    pyproject_path = base_dir / "pyproject.toml"
    if pyproject_path.is_file():
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            version = data.get("project", {}).get("version")
            if isinstance(version, str) and version:
                return version
        except OSError:
            pass
    return DEFAULT_APP_VERSION
