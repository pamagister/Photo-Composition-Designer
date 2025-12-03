# --- geometry helpers -----------------------------------------------------
def mm_to_px(mm: float | int, dpi: float | int = 300) -> int:
    """Convert millimeters to pixels based on DPI."""
    return int(round(float(mm) * dpi / 25.4))
