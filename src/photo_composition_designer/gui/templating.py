"""Shared Jinja2 template environment for the local web application."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))
