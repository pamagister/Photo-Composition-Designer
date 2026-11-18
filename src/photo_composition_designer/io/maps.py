"""Local map rendering service with a deterministic disk cache.

The small map is rendered server-side by :class:`MapRenderer` using bundled
Natural Earth shapefiles. No network access or third-party tiles are used.
Generated PNGs are cached by a key that captures every input that affects the
output: coordinate set, map geometry, colors, DPI and the local shapefile
version.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from photo_composition_designer.core.helpers import get_base_path
from photo_composition_designer.render.map import MapRenderer


@dataclass(frozen=True)
class MapRequest:
    """Inputs that fully determine a rendered map image."""

    coordinates: tuple[tuple[float, float], ...]
    width: int
    height: int
    minimal_extension: int
    background_color: tuple[int, int, int]
    text_color: tuple[int, int, int]
    dpi: int


def _shapefile_version() -> str:
    """Return a fingerprint of the bundled map shapefiles.

    The ``.shp`` file modification time and size are combined so that a
    refreshed Natural Earth extract invalidates the cache.
    """
    maps_root = get_base_path() / "res" / "maps"
    digest = hashlib.sha256()
    if maps_root.is_dir():
        for shp in sorted(maps_root.glob("*/*.shp")):
            stat = shp.stat()
            digest.update(shp.name.encode())
            digest.update(str(stat.st_mtime_ns).encode())
            digest.update(str(stat.st_size).encode())
    return digest.hexdigest()[:16]


def map_cache_key(request: MapRequest) -> str:
    """Return a deterministic cache key for a map request."""
    payload = {
        "coordinates": sorted(request.coordinates),
        "width": request.width,
        "height": request.height,
        "minimal_extension": request.minimal_extension,
        "background_color": list(request.background_color),
        "text_color": list(request.text_color),
        "dpi": request.dpi,
        "shapefile_version": _shapefile_version(),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class MapService:
    """Render and cache local maps for a set of coordinates."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = Path(cache_dir) / "maps"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.png"

    def render(self, request: MapRequest) -> Path:
        """Return a PNG file path for the map, generating it if not cached."""
        key = map_cache_key(request)
        destination = self._cache_path(key)
        if destination.is_file():
            return destination

        renderer = MapRenderer(
            mapHeight=request.height,
            mapWidth=request.width,
            minimalExtension=request.minimal_extension,
            backgroundColor=request.background_color,
            textColor1=request.text_color,
        )
        image = renderer.generate(list(request.coordinates))
        if not isinstance(image, Image.Image):
            raise RuntimeError("map renderer did not return a PIL image")

        tmp = destination.with_suffix(".tmp.png")
        image.save(tmp, format="PNG")
        tmp.replace(destination)
        return destination

    def cached_path(self, request: MapRequest) -> Path:
        """Return the cache path for a request without rendering it."""
        return self._cache_path(map_cache_key(request))
