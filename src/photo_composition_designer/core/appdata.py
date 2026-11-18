"""Platform-specific application directories for config, data and cache.

Environment overrides keep tests and portable installs isolated from the real
home directory. The central SQLite workspace and caches live under the user's
data directory, independent of any project.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "photo-composition-designer"
CONFIG_ENV = "PCD_CONFIG_DIR"
DATA_ENV = "PCD_DATA_DIR"
CACHE_ENV = "PCD_CACHE_DIR"

#: File name of the central SQLite workspace.
DATABASE_FILE_NAME = "workspace.sqlite3"


def _env_dir(name: str) -> Path | None:
    """Return an explicitly configured directory, or ``None``."""
    value = os.environ.get(name)
    return Path(value).expanduser() if value else None


def _windows_base(env_name: str, fallback: Path) -> Path:
    value = os.environ.get(env_name)
    return Path(value) if value else fallback


def config_dir() -> Path:
    """Directory holding the central configuration."""
    override = _env_dir(CONFIG_ENV)
    if override is not None:
        return override
    if sys.platform.startswith("win"):
        base = _windows_base("APPDATA", Path.home() / "AppData" / "Roaming")
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / APP_NAME


def data_dir() -> Path:
    """Directory holding the central database, thumbnails, previews and exports."""
    override = _env_dir(DATA_ENV)
    if override is not None:
        return override
    if sys.platform.startswith("win"):
        base = _windows_base("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        return base / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_NAME


def cache_dir() -> Path:
    """Disposable cache directory (thumbnails, previews, maps)."""
    override = _env_dir(CACHE_ENV)
    if override is not None:
        return override
    if sys.platform.startswith("win"):
        base = _windows_base("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        return base / APP_NAME / "cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / APP_NAME
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / APP_NAME


def workspace_path() -> Path:
    """Return the central SQLite workspace path."""
    return data_dir() / DATABASE_FILE_NAME


def ensure_directories() -> None:
    """Create the data and cache directories if they do not exist."""
    data_dir().mkdir(parents=True, exist_ok=True)
    cache_dir().mkdir(parents=True, exist_ok=True)
