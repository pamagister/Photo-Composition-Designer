from __future__ import annotations

import calendar
import logging
from datetime import datetime, timedelta
from pathlib import Path

import holidays
import pytz
from astral import LocationInfo
from astral.sun import sun
from babel.dates import get_day_names, get_month_names
from config_cli_gui.configtypes.font import Font
from PIL import Image, ImageDraw

from Photo_Composition_Designer.common.Anniversaries import Anniversaries
from Photo_Composition_Designer.common.MoonPhase import MoonPhase
from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.tools.Helpers import mm_to_px


class CalendarRenderer:
    """Responsible for rendering a weekly calendar strip with holidays,
    sun times and anniversaries.
    """

    def __init__(
        self,
        backgroundColor: tuple[int],
        fontLarge: Font,
        fontSmall: Font,
        fontHoliday: Font,
        language: str,
        startDate: datetime,
        holidayCountries: list[str],
        useShortDayNames: bool,
        useShortMonthNames: bool,
        marginSides: float,
        anniversaries: Anniversaries | None = None,
        dpi: int = 300,
    ) -> None:
        self.anniversaries = anniversaries or Anniversaries()

        self.backgroundColor = backgroundColor
        self.font_large: Font = fontLarge
        self.font_small: Font = fontSmall
        self.font_holiday: Font = fontHoliday

        self.language = language
        self.startDate = startDate
        self.holidayCountries = holidayCountries
        self.useShortDayNames = useShortDayNames
        self.useShortMonthNames = useShortMonthNames
        self.marginSides = marginSides
        self.dpi = dpi

        # Extract country code from locale ("de_DE" → "DE")
        country_code = language.split("_")[1].upper()

        self.localHolidays = self.get_combined_holidays(
            startDate.year,
            country_code,
            holidayCountries,
            language=self.language,
        )

    @classmethod
    def from_config(cls, config: ConfigParameterManager) -> CalendarRenderer:
        """Factory function to create CalendarGenerator using the config manager."""
        margin_sides_px = mm_to_px(config.layout.marginSides.value, config.size.dpi.value)

        # Resolve anniversaries config:
        # if a file path (or string) is provided, load it via Anniversaries
        anniv_cfg = config.general.anniversariesConfig.value
        if isinstance(anniv_cfg, (str, Path)):
            anniversaries_obj = Anniversaries(anniv_cfg)
        else:
            anniversaries_obj = anniv_cfg

        return cls(
            backgroundColor=config.style.backgroundColor.value.to_pil(),
            fontLarge=config.style.fontLarge.value,
            fontSmall=config.style.fontSmall.value,
            fontHoliday=config.style.fontAnniversaries.value,
            language=config.calendar.language.value,
            startDate=config.calendar.startDate.value,
            holidayCountries=[s.strip() for s in config.calendar.holidayCountries.value.split(",")],
            useShortDayNames=config.layout.useShortDayNames.value,
            useShortMonthNames=config.layout.useShortMonthNames.value,
            marginSides=margin_sides_px,
            anniversaries=anniversaries_obj,  # resolved object or None
            dpi=config.size.dpi.value,
        )

    # -------------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------------

    def generate(self, d: datetime, width: int | float, height: int | float) -> Image.Image:
        """Render full weekly calendar image."""
        width = int(width)
        height = int(height)
        week_dates = [d + timedelta(days=i) for i in range(7)]

        img = Image.new("RGB", (width, height), self.backgroundColor)
        draw = ImageDraw.Draw(img)

        # Header (month + year)
        month_name = self.get_month_name(
            week_dates[0].month,
            locale_name=self.language,
            abbreviation=self.useShortMonthNames,
        )
        header_text = f"{month_name} {str(d.year)[-2:]}"
        draw.text(
            (0, height - self.font_holiday.size * self.dpi / 25.4),
            header_text,
            font=self.font_large.get_image_font(self.dpi),
            fill=self.font_small.color.to_pil(),
            anchor="ld",
        )

        # Sun times for Europe/Berlin
        location = LocationInfo("Dresden", "Germany", "Europe/Berlin", 51.0504, 13.7373)
        tz = pytz.timezone("Europe/Berlin")
        sun_times = sun(location.observer, date=d)

        sunrise = sun_times["sunrise"].astimezone(tz).strftime("%H:%M")
        sunset = sun_times["sunset"].astimezone(tz).strftime("%H:%M")
        week_no = d.isocalendar().week

        sun_string = f"KW {week_no}  ● ↑ {sunrise}  ○ ↓ {sunset}"
        draw.text(
            (0, height),
            sun_string,
            font=self.font_holiday.get_image_font(self.dpi),
            fill=self.font_small.color.to_pil(),
            anchor="ld",
        )

        # Day columns
        month_cols, col_width = self.get_cols_property(width)

        for idx, day_date in enumerate(week_dates):
            x = self.marginSides + (idx + month_cols + 0.5) * col_width

            date_key = (day_date.day, day_date.month)
            holiday_name = self.localHolidays.get(day_date)

            is_weekend = day_date.weekday() >= 5
            is_holiday = day_date in self.localHolidays

            color_day = (
                self.font_holiday.color.to_pil()
                if (is_holiday or is_weekend)
                else self.font_large.color.to_pil()
            )

            # Day name
            day_name = self.get_day_name(day_date.weekday(), self.language)
            if self.useShortDayNames:
                day_name = day_name[:2]

            moon_symbol = MoonPhase.get_moon_phase_symbol_dark(day_date)
            if moon_symbol:
                day_name = f"{day_name} {moon_symbol}"

            draw.text(
                (
                    x,
                    height
                    - self.font_holiday.size * self.dpi / 25.4
                    - self.font_large.size * self.dpi / 25.4 * 1.15,
                ),
                day_name,
                font=self.font_small.get_image_font(self.dpi),
                fill=self.font_small.color.to_pil(),
                anchor="md",
            )

            draw.text(
                (x, height - self.font_holiday.size * self.dpi / 25.4),
                str(day_date.day),
                font=self.font_large.get_image_font(self.dpi),
                fill=color_day,
                anchor="md",
            )

            # Anniversaries + holidays
            label = None
            if date_key in self.anniversaries:
                label = self.anniversaries[date_key]
                if holiday_name:
                    label += f", {holiday_name}"
                draw.fill = self.font_large
            elif holiday_name:
                label = holiday_name

            if label:
                draw.text(
                    (x, height),
                    label,
                    font=self.font_holiday.get_image_font(self.dpi),
                    fill=self.font_holiday.color.to_pil(),
                    anchor="md",
                )

        return img

    def generateTitle(self, title: str, width: int | float, height: int | float) -> Image.Image:
        """Generates a title strip."""
        width = int(width)
        height = int(height)
        img = Image.new("RGB", (width, height), self.backgroundColor)
        draw = ImageDraw.Draw(img)

        font_large_pil = self.font_large.get_image_font(self.dpi)

        draw.text(
            (width // 2, height - self.font_holiday.size * self.dpi / 25.4),
            title,
            font=font_large_pil,
            fill=self.font_large.color.to_pil(),
            anchor="md",
        )
        return img

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def get_cols_property(self, width: int) -> tuple[float, float]:
        month_cols = 1.5 if self.useShortMonthNames else 4.0
        col_width = (width - 3 * self.marginSides) / (7.0 + month_cols)
        return month_cols, col_width

    @staticmethod
    def get_month_name(month: int, locale_name: str, abbreviation: bool = False) -> str:
        try:
            width = "abbreviated" if abbreviation else "wide"
            months = get_month_names(width=width, locale=locale_name)
            return months[month].rstrip(".")
        except Exception:
            # Fallback auf englische Namen wie bisher
            return calendar.month_abbr[month] if abbreviation else calendar.month_name[month]

    @staticmethod
    def get_day_name(day: int, locale_name: str) -> str:
        try:
            days = get_day_names(width="wide", locale=locale_name)
            return days[day]
        except Exception:
            # Fallback auf englische Namen wie bisher
            return calendar.day_name[day]

    @staticmethod
    def get_combined_holidays(
        year: int, country: str, subdivs: list[str], language: str | None = None
    ) -> holidays.HolidayBase:
        """Return combined country + subdivision holidays for year and optionally localised names.

        language: Optional locale string like 'de_DE' or 'en_US'. The function will extract
        the language code (e.g. 'de') and pass it to python-holidays so names are returned
        in the requested language when supported.
        """
        years = (year, year + 1)
        combined = holidays.HolidayBase()

        # Determine language code for python-holidays (e.g., 'de' from 'de_DE')
        lang_code = None
        if language:
            try:
                lang_code = language.split("_")[0]
            except Exception:
                lang_code = language

        # Load base country holidays with language if provided
        if lang_code:
            combined.update(holidays.country_holidays(country, years=years, language=lang_code))
        else:
            combined.update(holidays.country_holidays(country, years=years))

        # Load subdivisions (if any).
        # Handle errors per subdivision so one bad subdiv won't break all.
        for sub in subdivs or []:
            try:
                if lang_code:
                    combined.update(
                        holidays.country_holidays(
                            country, years=years, subdiv=sub, language=lang_code
                        )
                    )
                else:
                    combined.update(holidays.country_holidays(country, years=years, subdiv=sub))
            except Exception as e:
                logging.warning(f"Unable to load holiday subdivision {sub}: {e}")

        return combined


# -----------------------------------------------------------------------------
# Main helpers for production use
# -----------------------------------------------------------------------------


def main() -> None:
    import os

    from Photo_Composition_Designer.config.config import ConfigParameterManager

    config = ConfigParameterManager()
    cg = CalendarRenderer.from_config(config)

    # Create temp directory
    project_root = Path(__file__).resolve().parents[3]
    temp_dir = project_root / "temp"
    temp_dir.mkdir(exist_ok=True)

    title = config.general.compositionTitle.value + " " + str(config.calendar.startDate.value.year)
    first = True

    for w in range(config.calendar.collagesToGenerate.value):
        dt = config.calendar.startDate.value + timedelta(weeks=w - 2)

        if first:
            img = cg.generateTitle(
                title,
                width=int(config.size.width.value * config.size.dpi.value / 25.4),
                height=int(config.size.calendarHeight.value * config.size.dpi.value / 25.4),
            )
            first = False
        else:
            img = cg.generate(
                dt,
                width=int(config.size.width.value * config.size.dpi.value / 25.4),
                height=config.size.calendarHeight.value * config.size.dpi.value / 25.4,
            )

        path = os.path.join(temp_dir, f"calendar_{dt.year}-{dt.month:02d}-{dt.day:02d}.jpg")
        img.save(path)
        print("Generated:", path)


if __name__ == "__main__":
    main()
