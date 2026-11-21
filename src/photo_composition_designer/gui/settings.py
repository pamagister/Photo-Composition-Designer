"""Runtime settings for the local web application.

These settings are deliberately separate from the renderer ``Settings`` in
:mod:`photo_composition_designer.core.settings`. The web layer owns process
configuration such as host, port and log level, while renderer settings are
snapshotted per project.

A small set of genuinely global preferences (shared config files and the
object-detection model) is persisted to ``preferences.json`` in the
platform-specific configuration directory so it survives restarts and is not
captured in any single project snapshot.
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
from photo_composition_designer.core.model_assets import default_yolo_model_path

#: Preferences file holding the app-wide settings.
PREFERENCES_FILE_NAME = "preferences.json"


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
    object_detection_enabled: bool = False
    yolo_model_path: Path | None = None

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


def _preferences_path() -> Path:
    """Return the path of the app-wide preferences file."""
    return config_dir() / PREFERENCES_FILE_NAME


def _load_preferences() -> dict[str, object]:
    """Read the persisted preferences, returning an empty mapping on error."""
    path = _preferences_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_gui_settings() -> GuiSettings:
    """Return the local web settings, applying persisted global preferences.

    Environment overrides in :mod:`photo_composition_designer.core.appdata` are
    resolved when the default data and cache directories are created.
    """
    settings = GuiSettings()
    preferences = _load_preferences()
    anniversaries_path = preferences.get("anniversaries_path")
    locations_path = preferences.get("locations_path")
    yolo_model_path = preferences.get("yolo_model_path")
    return GuiSettings(
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        data_dir=settings.data_dir,
        cache_dir=settings.cache_dir,
        database_path=settings.database_path,
        anniversaries_path=Path(anniversaries_path) if anniversaries_path else None,
        locations_path=Path(locations_path) if locations_path else None,
        object_detection_enabled=bool(preferences.get("object_detection_enabled", False)),
        yolo_model_path=(Path(yolo_model_path) if yolo_model_path else default_yolo_model_path()),
    )


def _normalize_config_path(value: str, label: str) -> Path | None:
    """Resolve an optional configuration file path and require it to exist."""
    normalized = value.strip()
    path = Path(normalized).expanduser().resolve() if normalized else None
    if path is not None and not path.is_file():
        raise ValueError(f"{label} file does not exist: {path}")
    return path


def _normalize_model_path(value: str) -> Path:
    """Resolve the YOLO model path without requiring the file to exist yet.

    The model may legitimately be configured before it has been downloaded, so
    an empty value falls back to the OS-specific default location.
    """
    normalized = value.strip()
    if not normalized:
        return default_yolo_model_path()
    return Path(normalized).expanduser().resolve()


def _write_preferences(preferences: dict[str, object]) -> None:
    """Persist the preferences mapping atomically."""
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / PREFERENCES_FILE_NAME
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(preferences, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def save_paths(
    *,
    anniversaries_path: str = "",
    locations_path: str = "",
) -> tuple[Path | None, Path | None]:
    """Persist the app-wide anniversary and location file paths.

    Other preferences (object detection) are preserved unchanged.
    """
    anniversaries = _normalize_config_path(anniversaries_path, "anniversaries")
    locations = _normalize_config_path(locations_path, "locations")

    preferences = _load_preferences()
    preferences.update(
        {
            "anniversaries_path": str(anniversaries) if anniversaries else "",
            "locations_path": str(locations) if locations else "",
        }
    )
    _write_preferences(preferences)
    return anniversaries, locations


def save_app_settings(
    *,
    anniversaries_path: str = "",
    locations_path: str = "",
    object_detection_enabled: bool = False,
    yolo_model_path: str = "",
) -> tuple[Path | None, Path | None, Path]:
    """Persist all app-wide preferences and return the resolved paths."""
    anniversaries = _normalize_config_path(anniversaries_path, "anniversaries")
    locations = _normalize_config_path(locations_path, "locations")
    model = _normalize_model_path(yolo_model_path)

    preferences = _load_preferences()
    preferences.update(
        {
            "anniversaries_path": str(anniversaries) if anniversaries else "",
            "locations_path": str(locations) if locations else "",
            "object_detection_enabled": object_detection_enabled,
            "yolo_model_path": str(model),
        }
    )
    _write_preferences(preferences)
    return anniversaries, locations, model


def save_anniversaries_path(path: str) -> Path | None:
    """Backward-compatible wrapper that updates only the anniversary path."""
    stored = _load_preferences()
    locations_path = str(stored.get("locations_path", ""))
    return save_paths(anniversaries_path=path, locations_path=locations_path)[0]
