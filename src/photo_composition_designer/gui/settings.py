"""Runtime settings for the local web application.

These settings are deliberately separate from the renderer ``Settings`` in
:mod:`photo_composition_designer.core.settings`. The web layer owns process
configuration such as host, port and log level, while renderer settings are
snapshotted per project.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from photo_composition_designer.core.appdata import (
    DATABASE_FILE_NAME,
    config_dir,
)
from photo_composition_designer.core.appdata import (
    cache_dir as default_cache_dir,
)
from photo_composition_designer.core.appdata import (
    data_dir as default_data_dir,
)


@dataclass(frozen=True)
class GuiSettings:
    """Local server configuration and resolved application paths."""

    host: str = "127.0.0.1"
    port: int = 8767
    log_level: str = "info"
    data_dir: Path = field(default_factory=default_data_dir)
    cache_dir: Path = field(default_factory=default_cache_dir)
    database_path: Path | None = None
    anniversaries_path: Path | None = None
    locations_path: Path | None = None

    def workspace_path(self) -> Path:
        """Return the central SQLite workspace path."""
        return self.database_path or (self.data_dir / DATABASE_FILE_NAME)

    def thumbnail_dir(self) -> Path:
        """Return the thumbnail cache directory."""
        return self.cache_dir / "thumbnails"

    def preview_dir(self) -> Path:
        """Return the page preview cache directory."""
        return self.cache_dir / "previews"

    def export_dir(self) -> Path:
        """Return the web export output directory."""
        return self.cache_dir / "exports"

    def ensure_directories(self) -> None:
        """Create all writable application directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_dir().mkdir(parents=True, exist_ok=True)
        self.preview_dir().mkdir(parents=True, exist_ok=True)
        self.export_dir().mkdir(parents=True, exist_ok=True)
        self.workspace_path().parent.mkdir(parents=True, exist_ok=True)


def load_gui_settings() -> GuiSettings:
    """Return the default local web settings.

    Environment overrides in :mod:`photo_composition_designer.core.appdata` are
    resolved when the default data and cache directories are created.
    """
    settings = GuiSettings()
    preferences_path = config_dir() / "preferences.json"
    if not preferences_path.is_file():
        return settings
    with preferences_path.open("r", encoding="utf-8") as handle:
        preferences = json.load(handle)
    anniversaries_path = preferences.get("anniversaries_path")
    locations_path = preferences.get("locations_path")
    return GuiSettings(
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        data_dir=settings.data_dir,
        cache_dir=settings.cache_dir,
        database_path=settings.database_path,
        anniversaries_path=Path(anniversaries_path) if anniversaries_path else None,
        locations_path=Path(locations_path) if locations_path else None,
    )


def _normalize_config_path(value: str, label: str) -> Path | None:
    """Resolve an optional configuration file path and require it to exist."""
    normalized = value.strip()
    path = Path(normalized).expanduser().resolve() if normalized else None
    if path is not None and not path.is_file():
        raise ValueError(f"{label} file does not exist: {path}")
    return path


def save_paths(
    *,
    anniversaries_path: str = "",
    locations_path: str = "",
) -> tuple[Path | None, Path | None]:
    """Persist the app-wide anniversary and location file paths."""
    anniversaries = _normalize_config_path(anniversaries_path, "anniversaries")
    locations = _normalize_config_path(locations_path, "locations")

    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "preferences.json"
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "anniversaries_path": str(anniversaries) if anniversaries else "",
                    "locations_path": str(locations) if locations else "",
                },
                handle,
                indent=2,
            )
            handle.write("\n")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return anniversaries, locations


def save_anniversaries_path(path: str) -> Path | None:
    """Backward-compatible wrapper that updates only the anniversary path."""
    preferences_path = config_dir() / "preferences.json"
    locations_path = ""
    if preferences_path.is_file():
        try:
            stored = json.loads(preferences_path.read_text(encoding="utf-8"))
            locations_path = str(stored.get("locations_path", ""))
        except (OSError, json.JSONDecodeError):
            locations_path = ""
    return save_paths(anniversaries_path=path, locations_path=locations_path)[0]
