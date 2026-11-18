"""Thumbnail and preview generation with a disposable local cache."""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

DEFAULT_THUMBNAIL_SIZE = 320


def thumbnail_path(
    cache_dir: Path,
    photo_id: int,
    *,
    mtime: float | None,
    size: int = DEFAULT_THUMBNAIL_SIZE,
) -> Path:
    """Return the cache path for one photo thumbnail.

    The source modification time is part of the name so a rescanned file gets a
    fresh thumbnail without an explicit invalidation step.
    """
    stamp = int(mtime) if mtime is not None else 0
    return Path(cache_dir) / "thumbnails" / f"{photo_id}-{stamp}-{size}.jpg"


def create_thumbnail(
    source: Path,
    destination: Path,
    *,
    max_size: int = DEFAULT_THUMBNAIL_SIZE,
) -> None:
    """Create a JPEG thumbnail atomically.

    The source file is only read. Existing destination files are replaced only
    after the new thumbnail has been written successfully.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with Image.open(source) as image:
            thumbnail = image.convert("RGB")
            thumbnail.thumbnail((max_size, max_size))
            thumbnail.save(temporary, format="JPEG", quality=85, optimize=True)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
