"""Font value type used by the calendar renderer.

Replaces the ``config_cli_gui`` font type so the runtime no longer depends on
that package. The public shape (``get_image_font``, ``color``, ``name``,
``size``) matches the old type so renderer code and tests keep working.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import ImageFont

from photo_composition_designer.core.color import Color


def _list_system_fonts() -> list[str]:
    """Return a best-effort list of installed font file paths."""
    candidates: list[Path] = []
    if sys.platform.startswith("win"):
        candidates.append(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts")
    elif sys.platform == "darwin":
        candidates.extend(
            [
                Path("/System/Library/Fonts"),
                Path("/Library/Fonts"),
                Path.home() / "Library" / "Fonts",
            ]
        )
    else:
        candidates.extend(
            [
                Path("/usr/share/fonts"),
                Path("/usr/local/share/fonts"),
                Path.home() / ".fonts",
                Path.home() / ".local" / "share" / "fonts",
            ]
        )

    fonts: list[str] = []
    for directory in candidates:
        if directory.is_dir():
            for root, _dirs, files in os.walk(directory):
                for name in files:
                    if name.lower().endswith((".ttf", ".otf", ".ttc")):
                        fonts.append(str(Path(root) / name))
    return fonts


class Font:
    """Font with type name, size and color."""

    font_files = _list_system_fonts()
    font_names = sorted([os.path.basename(f) for f in font_files])
    font_files_sorted = sorted(font_files, key=os.path.basename)

    def __init__(self, font_type: str, size: float, color: Color) -> None:
        self.name = font_type
        self.size = size
        self.color = color

    def to_list(self) -> list[object]:
        """Return ``[name, size, hex]``."""
        return [self.name, self.size, self.color.to_hex()]

    @classmethod
    def from_list(cls, font_data: list[object]) -> Font:
        """Build from ``[name, size, color]``."""
        if len(font_data) < 3:
            return cls("Arial", 12, Color(0, 0, 0))
        font_type, size, color_val = font_data
        color = (
            Color.from_hex(color_val) if isinstance(color_val, str) else Color.from_list(color_val)
        )
        return cls(str(font_type), float(size), color)

    def to_str(self) -> str:
        """Return ``name, size, hex``."""
        return f"{self.name}, {self.size}, {self.color.to_hex()}"

    @classmethod
    def from_str(cls, font_init_str: str) -> Font:
        """Parse ``FontName, size, #rrggbb``."""
        if not isinstance(font_init_str, str):
            return cls("Arial", 12, Color(0, 0, 0))
        parts = [p.strip() for p in font_init_str.split(",")]
        if len(parts) < 3:
            return cls("Arial", 12, Color(0, 0, 0))
        font_name = parts[0]
        try:
            size = float(parts[1])
        except ValueError:
            size = 12.0
        color_raw = ",".join(parts[2:]).strip()
        color = Color.from_hex(color_raw)
        return cls(font_name, size, color)

    def get_image_font(self, dpi: float = 25.4) -> ImageFont.FreeTypeFont:
        """Return a PIL font scaled by ``dpi``.

        Falls back to the default PIL font when the named font cannot be
        loaded.
        """
        size = self.size * dpi / 25.4
        try:
            if self.name in self.font_names:
                idx = self.font_names.index(self.name)
                path = self.font_files_sorted[idx]
                return ImageFont.truetype(font=path, size=size)
        except Exception as error:  # noqa: BLE001 - fall back to default font
            print(f"Error loading font '{self.name}': {error}")
            try:
                return ImageFont.truetype(font="Arial.ttf", size=size)
            except Exception as fallback_error:  # noqa: BLE001
                print(f"Error loading fallback font 'Arial.ttf': {fallback_error}")
        return ImageFont.load_default(size=size)
