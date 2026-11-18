"""Small geometry and path helpers shared across the package."""

from __future__ import annotations

import sys
from pathlib import Path


def mm_to_px(mm: float | int, dpi: float | int = 300) -> int:
    """Convert millimeters to pixels based on DPI."""
    return int(round(float(mm) * dpi / 25.4))


def get_base_path() -> Path:
    """Return the base path for bundled resources.

    Under PyInstaller (``sys._MEIPASS``) this points at the temporary
    extraction directory; otherwise it is the repository/project root that
    holds the ``res/`` resource directory.
    """
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent.parent.parent
