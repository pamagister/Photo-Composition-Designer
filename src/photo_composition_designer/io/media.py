"""Safe source-media resolution and content type helpers."""

from __future__ import annotations

import mimetypes
from pathlib import Path

DEFAULT_MEDIA_TYPE = "application/octet-stream"


def resolve_source_path(source_root: str | Path, relative_path: str) -> Path:
    """Resolve a photo relative to its source root with containment validation.

    Raises:
        ValueError: If the resolved path escapes the source root.
    """
    root = Path(source_root).expanduser().resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and not candidate.is_relative_to(root):
        raise ValueError("photo path escapes the source root")
    return candidate


def media_type(path: str | Path) -> str:
    """Return a conservative media type for a source file."""
    return mimetypes.guess_type(Path(path).name)[0] or DEFAULT_MEDIA_TYPE
