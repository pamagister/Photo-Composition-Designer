"""Tests for layout loading, validation and slot-aware rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from photo_composition_designer.core.settings import Settings
from photo_composition_designer.layouts.loader import (
    LayoutValidationError,
    load_catalogue,
    load_layout_file,
    validate_layout,
)
from photo_composition_designer.render.slot_renderer import SlotAwareRenderer, SlotPhoto


def test_catalogue_loads_curated_layouts() -> None:
    catalogue = load_catalogue()
    assert {
        "single_full",
        "two_columns",
        "two_rows",
        "three_equal",
        "four_quadrants",
        "portrait_two_landscapes",
        "four_staggered_x",
        "four_staggered_y",
        "five_two_three",
        "five_split_center",
        "tiles_3_rows_4col",
        "tiles_3_rows_5col",
        "tiles_3_rows_mixed",
        "tiles_4_rows_5col",
        "tiles_4_rows_6col",
        "tiles_4_rows_mixed",
        "tiles_5_rows_5col",
        "tiles_5_rows_6col",
        "tiles_5_rows_mixed",
    } <= set(catalogue)
    assert catalogue["two_columns"].version == 1
    assert len(catalogue["two_columns"].slots) == 2
    assert len(catalogue["two_rows"].slots) == 2
    assert len(catalogue["four_staggered_x"].slots) == 4
    assert len(catalogue["four_staggered_y"].slots) == 4
    assert len(catalogue["five_two_three"].slots) == 5
    assert len(catalogue["five_split_center"].slots) == 5
    assert len(catalogue["tiles_3_rows_4col"].slots) == 12
    assert len(catalogue["tiles_3_rows_5col"].slots) == 15
    assert len(catalogue["tiles_3_rows_mixed"].slots) == 12
    assert len(catalogue["tiles_4_rows_5col"].slots) == 20
    assert len(catalogue["tiles_4_rows_6col"].slots) == 24
    assert len(catalogue["tiles_4_rows_mixed"].slots) == 24
    assert len(catalogue["tiles_5_rows_5col"].slots) == 25
    assert len(catalogue["tiles_5_rows_6col"].slots) == 30
    assert len(catalogue["tiles_5_rows_mixed"].slots) == 31


def test_every_catalogue_snapshot_roundtrips() -> None:
    for template in load_catalogue().values():
        snapshot = validate_layout(template.as_dict())
        assert snapshot == template


def test_validate_rejects_out_of_bounds_slot() -> None:
    with pytest.raises(LayoutValidationError):
        validate_layout(
            {
                "key": "bad",
                "version": 1,
                "name": "bad",
                "slots": [
                    {"key": "s", "x": 0.8, "y": 0.0, "width": 0.5, "height": 1.0},
                ],
            }
        )


def test_validate_rejects_duplicate_slot_keys() -> None:
    with pytest.raises(LayoutValidationError):
        validate_layout(
            {
                "key": "bad",
                "version": 1,
                "name": "bad",
                "slots": [
                    {"key": "s", "x": 0.0, "y": 0.0, "width": 0.5, "height": 1.0},
                    {"key": "s", "x": 0.5, "y": 0.0, "width": 0.5, "height": 1.0},
                ],
            }
        )


def test_validate_rejects_unsupported_crop_mode() -> None:
    with pytest.raises(LayoutValidationError):
        validate_layout(
            {
                "key": "bad",
                "version": 1,
                "name": "bad",
                "slots": [
                    {
                        "key": "s",
                        "x": 0.0,
                        "y": 0.0,
                        "width": 1.0,
                        "height": 1.0,
                        "crop_mode": "zoom",
                    },
                ],
            }
        )


def test_load_layout_file_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "custom.yaml"
    path.write_text(
        "key: custom\nversion: 1\nname: Custom\nslots:\n"
        "  - key: main\n    x: 0.0\n    y: 0.0\n    width: 1.0\n    height: 1.0\n",
        encoding="utf-8",
    )
    template = load_layout_file(path)
    assert template.key == "custom"
    assert template.slots[0].key == "main"


def test_slot_renderer_fills_slots(tmp_path: Path) -> None:
    catalogue = load_catalogue()
    layout = catalogue["two_columns"]

    left = tmp_path / "left.jpg"
    right = tmp_path / "right.jpg"
    Image.new("RGB", (100, 100), (255, 0, 0)).save(left)
    Image.new("RGB", (100, 100), (0, 0, 255)).save(right)

    renderer = SlotAwareRenderer(Settings())
    page = renderer.render(
        layout,
        {"left": SlotPhoto(left), "right": SlotPhoto(right)},
        page_width=200,
        page_height=100,
        background_color=(0, 0, 0),
    )

    assert page.size == (200, 100)
    red, green, blue = page.getpixel((25, 50))
    assert red > 200 and blue < 60
    red, green, blue = page.getpixel((175, 50))
    assert blue > 200 and red < 60


def test_slot_renderer_leaves_empty_slots_as_background(tmp_path: Path) -> None:
    catalogue = load_catalogue()
    layout = catalogue["two_columns"]
    left = tmp_path / "left.jpg"
    Image.new("RGB", (100, 100), (255, 0, 0)).save(left)

    renderer = SlotAwareRenderer(Settings())
    page = renderer.render(
        layout,
        {"left": SlotPhoto(left)},
        page_width=200,
        page_height=100,
        background_color=(0, 128, 0),
    )

    red, green, blue = page.getpixel((175, 50))
    assert (red, green, blue) == (0, 128, 0)
