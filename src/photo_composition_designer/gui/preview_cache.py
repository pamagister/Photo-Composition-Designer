"""Retention and request leases for immutable preview assets."""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping
from pathlib import Path

from fastapi.responses import FileResponse
from starlette.types import Receive, Scope, Send

PREVIEW_ASSET_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
PREVIEW_CACHE_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60
CURRENT_PREVIEW_WIDTHS = (200, 800)


class PreviewAssetLeases:
    """Prevent cleanup from removing preview files while responses are active."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[Path, int] = {}

    def acquire(self, path: Path) -> bool:
        """Acquire a response lease when the preview file exists."""
        with self._lock:
            if not path.is_file():
                return False
            self._active[path] = self._active.get(path, 0) + 1
            return True

    def release(self, path: Path) -> None:
        """Release a previously acquired response lease."""
        with self._lock:
            active_count = self._active.get(path)
            if active_count is None:
                raise RuntimeError(f"preview response lease is not active: {path}")
            if active_count == 1:
                del self._active[path]
            else:
                self._active[path] = active_count - 1

    def remove_if_expired(self, path: Path, *, cutoff: float) -> bool:
        """Remove an expired preview unless a response currently uses it."""
        with self._lock:
            if path in self._active:
                return False
            try:
                modified_at = path.stat().st_mtime
            except FileNotFoundError:
                return False
            if modified_at >= cutoff:
                return False
            try:
                path.unlink()
            except FileNotFoundError:
                return False
            return True


PREVIEW_ASSET_LEASES = PreviewAssetLeases()


class PreviewAssetFileResponse(FileResponse):
    """File response that releases its asset lease after the response completes."""

    def __init__(self, path: Path, *, headers: Mapping[str, str], media_type: str) -> None:
        self._leased_path = path
        super().__init__(path, headers=headers, media_type=media_type)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            PREVIEW_ASSET_LEASES.release(self._leased_path)


def cleanup_stale_preview_assets(
    preview_dir: Path,
    *,
    current_keys: set[str],
    now: float | None = None,
) -> int:
    """Remove expired, superseded JPEG previews and return the removal count."""
    pages_dir = Path(preview_dir) / "pages"
    if not pages_dir.is_dir():
        return 0

    current_time = time.time() if now is None else now
    cutoff = current_time - PREVIEW_ASSET_MAX_AGE_SECONDS
    removed = 0
    for path in pages_dir.glob("*.jpg"):
        if path.stem in current_keys:
            continue
        if PREVIEW_ASSET_LEASES.remove_if_expired(path, cutoff=cutoff):
            removed += 1
    return removed
