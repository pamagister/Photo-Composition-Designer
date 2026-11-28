"""Result models shared by layout-editing services."""

from __future__ import annotations

from dataclasses import dataclass

from photo_composition_designer.project.models import PhotoAsset


@dataclass(frozen=True)
class LayoutChangePreview:
    """Result of previewing or applying a layout change."""

    page_id: int
    layout_key: str
    layout_name: str
    slot_count: int
    preserved: tuple[tuple[int, str], ...]
    displaced: tuple[PhotoAsset, ...]

    @property
    def has_displaced(self) -> bool:
        return bool(self.displaced)
