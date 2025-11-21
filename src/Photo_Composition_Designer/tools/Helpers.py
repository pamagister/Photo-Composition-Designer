from PIL import ImageFont


# --- geometry helpers -----------------------------------------------------
def mm_to_px(mm: float | int, dpi: float | int = 300) -> int:
    """Convert millimeters to pixels based on DPI."""
    return int(round(float(mm) * dpi / 25.4))


# --- font helpers ---------------------------------------------------------


def load_font(name: str = "DejaVuSans.ttf", size: int = 10) -> ImageFont.FreeTypeFont:
    """Load a default TTF font, safely falling back to PIL's default."""
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return ImageFont.load_default()
