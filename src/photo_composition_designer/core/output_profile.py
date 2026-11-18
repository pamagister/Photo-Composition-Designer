"""Typed per-project output profile.

Every value that affects rendering is captured here so a project's output
cannot change when workspace defaults or the application are updated. The
profile is serialized into ``projects.output_profile_json`` and converted back
into the legacy :class:`~photo_composition_designer.core.settings.Settings`
shape only when a renderer needs it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from photo_composition_designer.core.color import Color
from photo_composition_designer.core.font import Font
from photo_composition_designer.core.helpers import mm_to_px
from photo_composition_designer.core.settings import Settings


class OutputProfileError(ValueError):
    """Raised when an output profile is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OutputProfileError(message)


def _bool_or(value: Any, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    _require(isinstance(value, bool), f"{field_name} must be a boolean")
    return value


def _int_or(
    value: Any,
    field_name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if value is None:
        return default
    _require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{field_name} must be an integer",
    )
    if minimum is not None:
        _require(value >= minimum, f"{field_name} must be >= {minimum}")
    if maximum is not None:
        _require(value <= maximum, f"{field_name} must be <= {maximum}")
    return value


def _float_or(
    value: Any, field_name: str, default: float, *, minimum: float | None = None
) -> float:
    if value is None:
        return default
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{field_name} must be a number",
    )
    number = float(value)
    if minimum is not None:
        _require(number >= minimum, f"{field_name} must be >= {minimum}")
    return number


def _str_or(value: Any, field_name: str, default: str) -> str:
    if value is None:
        return default
    _require(isinstance(value, str), f"{field_name} must be a string")
    return value


def _hex_or(value: Any, field_name: str, default: str) -> str:
    if value is None:
        return default
    text = _str_or(value, field_name, default).lstrip("#")
    _require(len(text) == 6, f"{field_name} must be a #rrggbb color")
    try:
        int(text, 16)
    except ValueError as exc:
        raise OutputProfileError(f"{field_name} must be a #rrggbb color") from exc
    return f"#{text.lower()}"


@dataclass(frozen=True)
class FontSpec:
    """Serializable font description used by the renderers."""

    name: str = "DejaVuSans.ttf"
    size: float = 9.0
    color: str = "#ffffff"

    def to_font(self) -> Font:
        """Return the renderer font value."""
        return Font(self.name, self.size, Color.from_hex(self.color))

    @classmethod
    def from_font(cls, font: Font) -> FontSpec:
        """Build a spec from a renderer font."""
        return cls(font.name, float(font.size), font.color.to_hex())

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "size": self.size, "color": self.color}

    @classmethod
    def from_dict(cls, data: Any) -> FontSpec:
        defaults = cls()
        if not isinstance(data, dict):
            return defaults
        return cls(
            _str_or(data.get("name"), "font name", defaults.name),
            _float_or(data.get("size"), "font size", defaults.size, minimum=0.0),
            _hex_or(data.get("color"), "font color", defaults.color),
        )


@dataclass(frozen=True)
class CalendarProfile:
    """Calendar strip and title settings."""

    use_calendar: bool = True
    language: str = "de_DE"
    holiday_countries: tuple[str, ...] = ("SN",)
    horizontal_orientation: bool = True
    use_short_day_names: bool = False
    use_short_month_names: bool = True
    title: str = "This is the title of the composition"

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_calendar": self.use_calendar,
            "language": self.language,
            "holiday_countries": list(self.holiday_countries),
            "horizontal_orientation": self.horizontal_orientation,
            "use_short_day_names": self.use_short_day_names,
            "use_short_month_names": self.use_short_month_names,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, data: Any) -> CalendarProfile:
        defaults = cls()
        if not isinstance(data, dict):
            return defaults
        raw_countries = data.get("holiday_countries")
        if raw_countries is None:
            countries = defaults.holiday_countries
        else:
            if isinstance(raw_countries, str):
                raw_countries = [part.strip() for part in raw_countries.split(",")]
            _require(isinstance(raw_countries, list), "holiday_countries must be a list")
            countries = tuple(
                _str_or(country, "holiday country", "").strip()
                for country in raw_countries
                if _str_or(country, "holiday country", "").strip()
            )
        return cls(
            use_calendar=_bool_or(data.get("use_calendar"), "use_calendar", defaults.use_calendar),
            language=_str_or(data.get("language"), "language", defaults.language),
            holiday_countries=countries,
            horizontal_orientation=_bool_or(
                data.get("horizontal_orientation"),
                "horizontal_orientation",
                defaults.horizontal_orientation,
            ),
            use_short_day_names=_bool_or(
                data.get("use_short_day_names"),
                "use_short_day_names",
                defaults.use_short_day_names,
            ),
            use_short_month_names=_bool_or(
                data.get("use_short_month_names"),
                "use_short_month_names",
                defaults.use_short_month_names,
            ),
            title=_str_or(data.get("title"), "title", defaults.title),
        )


@dataclass(frozen=True)
class StyleProfile:
    """Background and typography settings."""

    background_color: str = "#141414"
    font_large: FontSpec = field(default_factory=lambda: FontSpec("DejaVuSans.ttf", 9.0, "#ffffff"))
    font_small: FontSpec = field(default_factory=lambda: FontSpec("DejaVuSans.ttf", 2.5, "#969696"))
    font_description: FontSpec = field(
        default_factory=lambda: FontSpec("DejaVuSans.ttf", 2.5, "#969696")
    )
    font_anniversaries: FontSpec = field(
        default_factory=lambda: FontSpec("DejaVuSans.ttf", 2.0, "#ff0000")
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "background_color": self.background_color,
            "font_large": self.font_large.to_dict(),
            "font_small": self.font_small.to_dict(),
            "font_description": self.font_description.to_dict(),
            "font_anniversaries": self.font_anniversaries.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> StyleProfile:
        defaults = cls()
        if not isinstance(data, dict):
            return defaults
        return cls(
            background_color=_hex_or(
                data.get("background_color"), "background_color", defaults.background_color
            ),
            font_large=FontSpec.from_dict(data.get("font_large")),
            font_small=FontSpec.from_dict(data.get("font_small")),
            font_description=FontSpec.from_dict(data.get("font_description")),
            font_anniversaries=FontSpec.from_dict(data.get("font_anniversaries")),
        )


@dataclass(frozen=True)
class GeoProfile:
    """Map rendering settings."""

    use_photo_location_maps: bool = True
    minimal_extension: int = 7
    map_width: int = 20
    map_height: int = 20

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_photo_location_maps": self.use_photo_location_maps,
            "minimal_extension": self.minimal_extension,
            "map_width": self.map_width,
            "map_height": self.map_height,
        }

    @classmethod
    def from_dict(cls, data: Any) -> GeoProfile:
        defaults = cls()
        if not isinstance(data, dict):
            return defaults
        return cls(
            use_photo_location_maps=_bool_or(
                data.get("use_photo_location_maps"),
                "use_photo_location_maps",
                defaults.use_photo_location_maps,
            ),
            minimal_extension=_int_or(
                data.get("minimal_extension"),
                "minimal_extension",
                defaults.minimal_extension,
                minimum=0,
            ),
            map_width=_int_or(data.get("map_width"), "map_width", defaults.map_width, minimum=1),
            map_height=_int_or(
                data.get("map_height"), "map_height", defaults.map_height, minimum=1
            ),
        )


@dataclass(frozen=True)
class SizeProfile:
    """Page geometry and output size settings."""

    width: int = 216
    height: int = 154
    calendar_height: int = 18
    dpi: int = 300
    jpeg_quality: int = 90

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "calendar_height": self.calendar_height,
            "dpi": self.dpi,
            "jpeg_quality": self.jpeg_quality,
        }

    @classmethod
    def from_dict(cls, data: Any) -> SizeProfile:
        defaults = cls()
        if not isinstance(data, dict):
            return defaults
        return cls(
            width=_int_or(data.get("width"), "width", defaults.width, minimum=1),
            height=_int_or(data.get("height"), "height", defaults.height, minimum=1),
            calendar_height=_int_or(
                data.get("calendar_height"),
                "calendar_height",
                defaults.calendar_height,
                minimum=0,
            ),
            dpi=_int_or(data.get("dpi"), "dpi", defaults.dpi, minimum=1),
            jpeg_quality=_int_or(
                data.get("jpeg_quality"),
                "jpeg_quality",
                defaults.jpeg_quality,
                minimum=1,
                maximum=100,
            ),
        )


@dataclass(frozen=True)
class LayoutProfile:
    """Spacing, margins and layout feature toggles."""

    margin_top: int = 6
    margin_bottom: int = 3
    margin_sides: int = 3
    spacing: int = 2
    use_rounded_corners: bool = True
    image_score_factor: float = 2.0
    use_photo_description: bool = True
    generate_pdf: bool = True
    object_recognition: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "margin_top": self.margin_top,
            "margin_bottom": self.margin_bottom,
            "margin_sides": self.margin_sides,
            "spacing": self.spacing,
            "use_rounded_corners": self.use_rounded_corners,
            "image_score_factor": self.image_score_factor,
            "use_photo_description": self.use_photo_description,
            "generate_pdf": self.generate_pdf,
            "object_recognition": self.object_recognition,
        }

    @classmethod
    def from_dict(cls, data: Any) -> LayoutProfile:
        defaults = cls()
        if not isinstance(data, dict):
            return defaults
        return cls(
            margin_top=_int_or(
                data.get("margin_top"), "margin_top", defaults.margin_top, minimum=0
            ),
            margin_bottom=_int_or(
                data.get("margin_bottom"),
                "margin_bottom",
                defaults.margin_bottom,
                minimum=0,
            ),
            margin_sides=_int_or(
                data.get("margin_sides"), "margin_sides", defaults.margin_sides, minimum=0
            ),
            spacing=_int_or(data.get("spacing"), "spacing", defaults.spacing, minimum=0),
            use_rounded_corners=_bool_or(
                data.get("use_rounded_corners"),
                "use_rounded_corners",
                defaults.use_rounded_corners,
            ),
            image_score_factor=_float_or(
                data.get("image_score_factor"),
                "image_score_factor",
                defaults.image_score_factor,
                minimum=0.0,
            ),
            use_photo_description=_bool_or(
                data.get("use_photo_description"),
                "use_photo_description",
                defaults.use_photo_description,
            ),
            generate_pdf=_bool_or(data.get("generate_pdf"), "generate_pdf", defaults.generate_pdf),
            object_recognition=_bool_or(
                data.get("object_recognition"),
                "object_recognition",
                defaults.object_recognition,
            ),
        )


@dataclass(frozen=True)
class OutputProfile:
    """Complete, serializable snapshot of a project's output settings."""

    calendar: CalendarProfile = field(default_factory=CalendarProfile)
    style: StyleProfile = field(default_factory=StyleProfile)
    geo: GeoProfile = field(default_factory=GeoProfile)
    size: SizeProfile = field(default_factory=SizeProfile)
    layout: LayoutProfile = field(default_factory=LayoutProfile)

    @classmethod
    def default(cls) -> OutputProfile:
        """Return the profile snapshotted from the current application defaults."""
        return cls.from_settings(Settings())

    @classmethod
    def from_settings(cls, settings: Settings) -> OutputProfile:
        """Build a profile from a renderer settings object."""
        return cls(
            calendar=CalendarProfile(
                use_calendar=settings.calendar.useCalendar.value,
                language=settings.calendar.language.value,
                holiday_countries=tuple(
                    part.strip()
                    for part in settings.calendar.holidayCountries.value.split(",")
                    if part.strip()
                ),
                horizontal_orientation=settings.calendar.horizontalOrientation.value,
                use_short_day_names=settings.layout.useShortDayNames.value,
                use_short_month_names=settings.layout.useShortMonthNames.value,
                title=settings.general.compositionTitle.value,
            ),
            style=StyleProfile(
                background_color=settings.style.backgroundColor.value.to_hex(),
                font_large=FontSpec.from_font(settings.style.fontLarge.value),
                font_small=FontSpec.from_font(settings.style.fontSmall.value),
                font_description=FontSpec.from_font(settings.style.fontDescription.value),
                font_anniversaries=FontSpec.from_font(settings.style.fontAnniversaries.value),
            ),
            geo=GeoProfile(
                use_photo_location_maps=settings.geo.usePhotoLocationMaps.value,
                minimal_extension=settings.geo.minimalExtension.value,
                map_width=settings.size.mapWidth.value,
                map_height=settings.size.mapHeight.value,
            ),
            size=SizeProfile(
                width=settings.size.width.value,
                height=settings.size.height.value,
                calendar_height=settings.size.calendarHeight.value,
                dpi=settings.size.dpi.value,
                jpeg_quality=settings.size.jpgQuality.value,
            ),
            layout=LayoutProfile(
                margin_top=settings.layout.marginTop.value,
                margin_bottom=settings.layout.marginBottom.value,
                margin_sides=settings.layout.marginSides.value,
                spacing=settings.layout.spacing.value,
                use_rounded_corners=settings.layout.useRoundedCorners.value,
                image_score_factor=settings.layout.imageScoreFactor.value,
                use_photo_description=settings.layout.usePhotoDescription.value,
                generate_pdf=settings.layout.generatePdf.value,
                object_recognition=bool(settings.layout.objectRecognition),
            ),
        )

    def to_settings(self) -> Settings:
        """Return a legacy settings object populated from this profile."""
        settings = Settings()
        settings.general.compositionTitle.value = self.calendar.title
        settings.calendar.useCalendar.value = self.calendar.use_calendar
        settings.calendar.language.value = self.calendar.language
        settings.calendar.holidayCountries.value = ",".join(self.calendar.holiday_countries)
        settings.calendar.horizontalOrientation.value = self.calendar.horizontal_orientation
        settings.style.backgroundColor.value = Color.from_hex(self.style.background_color)
        settings.style.fontLarge.value = self.style.font_large.to_font()
        settings.style.fontSmall.value = self.style.font_small.to_font()
        settings.style.fontDescription.value = self.style.font_description.to_font()
        settings.style.fontAnniversaries.value = self.style.font_anniversaries.to_font()
        settings.geo.usePhotoLocationMaps.value = self.geo.use_photo_location_maps
        settings.geo.minimalExtension.value = self.geo.minimal_extension
        settings.size.width.value = self.size.width
        settings.size.height.value = self.size.height
        settings.size.calendarHeight.value = self.size.calendar_height
        settings.size.mapWidth.value = self.geo.map_width
        settings.size.mapHeight.value = self.geo.map_height
        settings.size.dpi.value = self.size.dpi
        settings.size.jpgQuality.value = self.size.jpeg_quality
        settings.layout.marginTop.value = self.layout.margin_top
        settings.layout.marginBottom.value = self.layout.margin_bottom
        settings.layout.marginSides.value = self.layout.margin_sides
        settings.layout.spacing.value = self.layout.spacing
        settings.layout.useRoundedCorners.value = self.layout.use_rounded_corners
        settings.layout.imageScoreFactor.value = self.layout.image_score_factor
        settings.layout.useShortDayNames.value = self.calendar.use_short_day_names
        settings.layout.useShortMonthNames.value = self.calendar.use_short_month_names
        settings.layout.usePhotoDescription.value = self.layout.use_photo_description
        settings.layout.generatePdf.value = self.layout.generate_pdf
        settings.layout.objectRecognition = self.layout.object_recognition
        return settings

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "calendar": self.calendar.to_dict(),
            "style": self.style.to_dict(),
            "geo": self.geo.to_dict(),
            "size": self.size.to_dict(),
            "layout": self.layout.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Any) -> OutputProfile:
        """Build a profile from stored JSON, filling missing values with defaults."""
        if not isinstance(data, dict):
            return cls()
        return cls(
            calendar=CalendarProfile.from_dict(data.get("calendar")),
            style=StyleProfile.from_dict(data.get("style")),
            geo=GeoProfile.from_dict(data.get("geo")),
            size=SizeProfile.from_dict(data.get("size")),
            layout=LayoutProfile.from_dict(data.get("layout")),
        )

    def profile_hash(self) -> str:
        """Return a stable short hash of every output-affecting value."""
        payload = json.dumps(self.to_dict(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()[:16]

    def page_size_px(self) -> tuple[int, int]:
        """Return the page width and height in pixels."""
        return (
            mm_to_px(self.size.width, self.size.dpi),
            mm_to_px(self.size.height, self.size.dpi),
        )


__all__ = [
    "CalendarProfile",
    "FontSpec",
    "GeoProfile",
    "LayoutProfile",
    "OutputProfile",
    "OutputProfileError",
    "SizeProfile",
    "StyleProfile",
]
