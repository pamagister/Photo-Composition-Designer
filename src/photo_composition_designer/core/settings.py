"""Typed application settings replacing the old ``config_cli_gui`` manager.

The renderer stack historically accessed configuration through
``config_cli_gui`` ``ConfigParameter`` objects that exposed a ``.value``
attribute and category groups (``config.size.dpi.value``,
``config.style.backgroundColor.value.to_pil()``). To remove the runtime
dependency on ``config_cli_gui`` while keeping the rendering code and its
tests stable, this module provides lightweight value wrappers that preserve
that exact access shape.

Each category is a plain dataclass whose fields are :class:`Param` instances.
``Settings`` exposes the same categories and a ``persist_last_used`` flag for
API compatibility with the old manager constructor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Generic, TypeVar

from photo_composition_designer.core.color import Color
from photo_composition_designer.core.font import Font

T = TypeVar("T")


@dataclass
class Param(Generic[T]):
    """A single configuration parameter with a typed value.

    Mirrors the subset of ``config_cli_gui.ConfigParameter`` used by the
    rendering stack: ``value`` access plus optional metadata.
    """

    value: T
    name: str = ""
    help: str = ""


@dataclass
class GeneralConfig:
    """GENERAL category."""

    photoDirectory: Param[Path] = field(
        default_factory=lambda: Param(Path("images"), "photoDirectory")
    )
    anniversariesConfig: Param[Path] = field(
        default_factory=lambda: Param(Path("anniversaries.ini"), "anniversariesConfig")
    )
    locationsConfig: Param[Path] = field(
        default_factory=lambda: Param(Path("locations_en.ini"), "locationsConfig")
    )
    compositionTitle: Param[str] = field(
        default_factory=lambda: Param("This is the title of the composition", "compositionTitle")
    )


@dataclass
class CalendarConfig:
    """CALENDAR category."""

    useCalendar: Param[bool] = field(default_factory=lambda: Param(True, "useCalendar"))
    language: Param[str] = field(default_factory=lambda: Param("de_DE", "language"))
    holidayCountries: Param[str] = field(default_factory=lambda: Param("SN", "holidayCountries"))
    startDate: Param[datetime] = field(
        default_factory=lambda: Param(datetime.fromisoformat("2025-12-29"), "startDate")
    )
    collagesToGenerate: Param[int] = field(default_factory=lambda: Param(53, "collagesToGenerate"))
    horizontalOrientation: Param[bool] = field(
        default_factory=lambda: Param(True, "horizontalOrientation")
    )
    useTitlePage: Param[bool] = field(default_factory=lambda: Param(True, "useTitlePage"))


@dataclass
class StyleConfig:
    """STYLE category."""

    backgroundColor: Param[Color] = field(
        default_factory=lambda: Param(Color(20, 20, 20), "backgroundColor")
    )
    fontLarge: Param[Font] = field(
        default_factory=lambda: Param(Font("DejaVuSans.ttf", 9, Color(255, 255, 255)), "fontLarge")
    )
    fontSmall: Param[Font] = field(
        default_factory=lambda: Param(
            Font("DejaVuSans.ttf", 2.5, Color(150, 150, 150)), "fontSmall"
        )
    )
    fontDescription: Param[Font] = field(
        default_factory=lambda: Param(
            Font("DejaVuSans.ttf", 2.5, Color(150, 150, 150)), "fontDescription"
        )
    )
    fontAnniversaries: Param[Font] = field(
        default_factory=lambda: Param(
            Font("DejaVuSans.ttf", 2.0, Color(255, 0, 0)), "fontAnniversaries"
        )
    )


@dataclass
class GeoConfig:
    """GEO category."""

    mapMode: Param[str] = field(default_factory=lambda: Param("auto", "mapMode"))
    minimalExtension: Param[int] = field(default_factory=lambda: Param(7, "minimalExtension"))


@dataclass
class SizeConfig:
    """SIZE category."""

    width: Param[int] = field(default_factory=lambda: Param(216, "width"))
    height: Param[int] = field(default_factory=lambda: Param(154, "height"))
    calendarHeight: Param[int] = field(default_factory=lambda: Param(18, "calendarHeight"))
    mapSize: Param[int] = field(default_factory=lambda: Param(20, "mapSize"))
    dpi: Param[int] = field(default_factory=lambda: Param(300, "dpi"))
    jpgQuality: Param[int] = field(default_factory=lambda: Param(90, "jpgQuality"))


@dataclass
class LayoutConfig:
    """LAYOUT category."""

    marginTop: Param[int] = field(default_factory=lambda: Param(6, "marginTop"))
    marginBottom: Param[int] = field(default_factory=lambda: Param(3, "marginBottom"))
    marginSides: Param[int] = field(default_factory=lambda: Param(3, "marginSides"))
    spacing: Param[int] = field(default_factory=lambda: Param(2, "spacing"))
    textMargin: Param[float] = field(default_factory=lambda: Param(1.5, "textMargin"))
    descriptionAlignment: Param[str] = field(
        default_factory=lambda: Param("left", "descriptionAlignment")
    )
    useRoundedCorners: Param[bool] = field(default_factory=lambda: Param(True, "useRoundedCorners"))
    imageScoreFactor: Param[float] = field(default_factory=lambda: Param(0.3, "imageScoreFactor"))
    useShortDayNames: Param[bool] = field(default_factory=lambda: Param(False, "useShortDayNames"))
    useShortMonthNames: Param[bool] = field(
        default_factory=lambda: Param(True, "useShortMonthNames")
    )
    usePhotoDescription: Param[bool] = field(
        default_factory=lambda: Param(True, "usePhotoDescription")
    )
    generatePdf: Param[bool] = field(default_factory=lambda: Param(True, "generatePdf"))


@dataclass
class Settings:
    """Aggregate settings object with the same shape as the old manager."""

    general: GeneralConfig = field(default_factory=GeneralConfig)
    calendar: CalendarConfig = field(default_factory=CalendarConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    geo: GeoConfig = field(default_factory=GeoConfig)
    size: SizeConfig = field(default_factory=SizeConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)

    def __init__(self, persist_last_used: bool = True) -> None:
        self.general = GeneralConfig()
        self.calendar = CalendarConfig()
        self.style = StyleConfig()
        self.geo = GeoConfig()
        self.size = SizeConfig()
        self.layout = LayoutConfig()
        self.persist_last_used = persist_last_used

    def get_cli_parameters(self) -> list[Param[object]]:
        """Return parameters marked as CLI-exposed (compatibility shim)."""
        return [self.general.photoDirectory, self.calendar.startDate]
