import sys
from pathlib import Path


def get_base_path() -> Path:
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # beim gebauten Executable
    else:
        base = Path(__file__).resolve().parent.parent
    return base
