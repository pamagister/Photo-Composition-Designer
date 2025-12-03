import os
from pathlib import Path

from PIL import ImageFont


# --- geometry helpers -----------------------------------------------------
def mm_to_px(mm: float | int, dpi: float | int = 300) -> int:
    """Convert millimeters to pixels based on DPI."""
    return int(round(float(mm) * dpi / 25.4))


# --- font helpers ---------------------------------------------------------


def list_system_fonts() -> list[str]:
    font_dirs = [
        "/usr/share/fonts",  # Linux allgemein
        "/usr/local/share/fonts",  # Linux lokal
        str(Path.home() / ".fonts"),  # Linux User-Fonts
        "/Library/Fonts",  # macOS
        "/System/Library/Fonts",  # macOS
        "C:/Windows/Fonts",  # Windows
    ]

    fonts = []
    for d in font_dirs:
        if os.path.isdir(d):
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".ttf", ".otf")):
                        fonts.append(os.path.join(root, f))
    return fonts


def load_font(name: str = "DejaVuSans.ttf", size: int = 10) -> ImageFont.FreeTypeFont:
    """Load a default TTF font, safely falling back to PIL's default."""
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        print(f"Error loading font {name}. Available fonts: \n")
        print("\n".join(list_system_fonts()))
        font: ImageFont.FreeTypeFont = ImageFont.load_default(size)
        return font
