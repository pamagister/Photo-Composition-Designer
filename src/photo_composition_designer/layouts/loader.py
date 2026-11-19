"""Loading and validation of versioned YAML layout templates.

A layout file describes named slots with normalized coordinates in ``[0, 1]``.
Users can drop additional ``*.yaml`` files into the user layout directory
without writing code. Each layout is copied into an immutable per-project
snapshot so later application changes never silently alter a saved page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from photo_composition_designer.core.appdata import data_dir

VALID_CROP_MODES = frozenset({"cover", "contain", "stretch"})


class LayoutValidationError(ValueError):
    """Raised when a layout definition is malformed."""


@dataclass(frozen=True)
class SlotTemplate:
    """A single named slot in a layout template."""

    key: str
    x: float
    y: float
    width: float
    height: float
    crop_mode: str = "cover"


@dataclass(frozen=True)
class LayoutTemplate:
    """A versioned, validated layout template."""

    key: str
    version: int
    name: str
    slots: tuple[SlotTemplate, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation for snapshots."""
        return {
            "key": self.key,
            "version": self.version,
            "name": self.name,
            "slots": [
                {
                    "key": slot.key,
                    "x": slot.x,
                    "y": slot.y,
                    "width": slot.width,
                    "height": slot.height,
                    "crop_mode": slot.crop_mode,
                }
                for slot in self.slots
            ],
        }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LayoutValidationError(message)


def validate_layout(data: dict[str, Any]) -> LayoutTemplate:
    """Validate a raw layout mapping and return a :class:`LayoutTemplate`.

    Raises:
        LayoutValidationError: If bounds, keys, positions, dimensions or crop
            modes are invalid.
    """
    _require(isinstance(data, dict), "layout must be a mapping")
    key = data.get("key")
    version = data.get("version")
    name = data.get("name")
    slots = data.get("slots")

    _require(isinstance(key, str) and key.strip(), "layout key must be a non-empty string")
    _require(isinstance(version, int) and version >= 1, "layout version must be >= 1")
    _require(isinstance(name, str) and name.strip(), "layout name must be a non-empty string")
    _require(isinstance(slots, list) and slots, "layout must declare at least one slot")

    seen_keys: set[str] = set()
    seen_positions: set[tuple[float, float]] = set()
    templates: list[SlotTemplate] = []

    for index, raw in enumerate(slots):
        _require(isinstance(raw, dict), f"slot {index} must be a mapping")
        slot_key = raw.get("key")
        _require(
            isinstance(slot_key, str) and slot_key.strip(),
            f"slot {index} key must be a non-empty string",
        )
        _require(slot_key not in seen_keys, f"duplicate slot key: {slot_key}")
        seen_keys.add(slot_key)

        x = float(raw.get("x", 0.0))
        y = float(raw.get("y", 0.0))
        width = float(raw.get("width", 0.0))
        height = float(raw.get("height", 0.0))
        crop_mode = str(raw.get("crop_mode", "cover"))

        _require(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0, f"slot {slot_key} origin out of bounds")
        _require(0.0 < width <= 1.0 and 0.0 < height <= 1.0, f"slot {slot_key} size invalid")
        _require(
            x + width <= 1.0 + 1e-9 and y + height <= 1.0 + 1e-9,
            f"slot {slot_key} extends beyond the page",
        )
        _require(
            (x, y) not in seen_positions,
            f"duplicate slot position: ({x}, {y})",
        )
        seen_positions.add((x, y))
        _require(
            crop_mode in VALID_CROP_MODES,
            f"slot {slot_key} has unsupported crop_mode: {crop_mode}",
        )
        templates.append(
            SlotTemplate(
                key=slot_key,
                x=x,
                y=y,
                width=width,
                height=height,
                crop_mode=crop_mode,
            )
        )

    return LayoutTemplate(key=key, version=version, name=name, slots=tuple(templates))


def load_layout_file(path: str | Path) -> LayoutTemplate:
    """Load and validate one YAML layout file."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return validate_layout(data)


def layout_directories() -> list[Path]:
    """Return built-in and user layout directories in load order."""
    builtin = Path(__file__).resolve().parent / "layouts"
    user = data_dir() / "layouts"
    return [builtin, user]


def load_catalogue() -> dict[str, LayoutTemplate]:
    """Load all layouts from built-in and user directories.

    Built-in layouts load first; user layouts with the same key and version
    override them so users can customise a shipped template without editing
    package code. The returned mapping is ordered by slot count (ascending)
    so consumers can present layouts from fewest to most images without
    re-sorting.
    """
    catalogue: dict[str, LayoutTemplate] = {}
    for directory in layout_directories():
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.yaml")):
            template = load_layout_file(path)
            catalogue[template.key] = template
    return dict(
        sorted(
            catalogue.items(),
            key=lambda item: (len(item[1].slots), item[1].name.lower(), item[0]),
            reverse=False,
        )
    )
