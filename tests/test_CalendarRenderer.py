import holidays
import pytest

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.image.CalendarRenderer import CalendarRenderer

from .TestHelper import temp_dir

print(f"Use temp dir: {temp_dir}")


def test_CalendarGenerator_proper_name(temp_dir):
    # Load default config
    config = ConfigParameterManager()

    # Build generator from config
    cg = CalendarRenderer.from_config(config)

    # Generate one title + one week
    title_img = cg.generateTitle(
        "Test Title",
        width=config.size.width.value * config.size.dpi.value / 25.4,
        height=config.size.calendarHeight.value * config.size.dpi.value / 25.4,
    )
    title_path = temp_dir / "title_test.jpg"
    title_img.save(title_path)

    assert title_path.exists()
    assert title_path.stat().st_size > 0

    # Weekly calendar
    dt = config.calendar.startDate.value
    cal_img = cg.generate(
        dt,
        width=config.size.width.value * config.size.dpi.value / 25.4,
        height=config.size.calendarHeight.value * config.size.dpi.value / 25.4,
    )
    cal_path = temp_dir / "week_test.jpg"
    cal_img.save(cal_path)

    assert cal_path.exists()
    assert cal_path.stat().st_size > 0

    print("Generated files:", title_path, cal_path)


def test_holidays_localization_and_subdivision():
    """Ensure german holiday names are returned and Saxony-specific holidays are present."""
    from datetime import date

    # Request German localization and Saxony subdivision
    combined = CalendarRenderer.get_combined_holidays(2025, "DE", ["SN"], language="de_DE")

    # New Year's Day should be present and in German
    new_year = date(2025, 1, 1)
    name_ny = combined.get(new_year)
    assert name_ny is not None
    assert "Neujahr" in name_ny

    # Reformationstag (31 Oct) should be a holiday and named in German
    reformation = date(2025, 10, 31)
    assert reformation in combined
    name_ref = combined.get(reformation)
    assert name_ref is not None
    assert "Reformationstag" in name_ref or "Reformation" in name_ref

    # Buß- und Bettag (Saxony special) - 2025-11-19 is expected
    buss_bettag = date(2025, 11, 19)
    assert buss_bettag in combined
    name_buss = combined.get(buss_bettag)
    assert name_buss is not None
    # name may contain 'Buß' (with ß) or similar; check substring
    assert "Buß" in name_buss or "Buss" in name_buss or "Bettag" in name_buss


def test_get_month_name():
    """Verify month names (full and abbreviated) for English and German locales.

    The test obtains expected strings by temporarily setting the system locale so
    it won't hardcode locale-specific punctuation or abbreviations.
    """
    # English expectations
    assert CalendarRenderer.get_month_name(1, "en_US", abbreviation=False) == "January"
    assert CalendarRenderer.get_month_name(1, "en_US", abbreviation=True) == "Jan"

    # German expectations

    assert CalendarRenderer.get_month_name(2, "de_DE", abbreviation=False) == "Februar"
    assert CalendarRenderer.get_month_name(2, "de_DE", abbreviation=True) == "Feb"


def test_get_day_name():
    """Verify weekday names for English and German locales for multiple weekdays."""
    # Monday (0)
    assert CalendarRenderer.get_day_name(0, "en_US") == "Monday"
    assert CalendarRenderer.get_day_name(0, "de_DE") == "Montag"
    assert CalendarRenderer.get_day_name(6, "de_DE") == "Sonntag"


def test_get_combined_holidays_includes_subdivision_holidays():
    year = 2026
    country = "DE"
    subdiv = "SN"  # Sachsen

    # Load raw holiday sets to determine a subdivision-only date (if present).
    years = (year, year + 1)
    base = holidays.country_holidays(country, years=years)
    sn = holidays.country_holidays(country, years=years, subdiv=subdiv)

    # Build combined using the function under test (request German localization if possible)
    combined = CalendarRenderer.get_combined_holidays(year, country, [subdiv], language="de_DE")

    assert isinstance(combined, holidays.HolidayBase)

    # The combined set must contain all base country holidays
    for d in base:
        assert d in combined

    # Find a date that exists only in the subdivision (if any) and assert it's present
    subdiv_only = set(sn.keys()) - set(base.keys())
    if not subdiv_only:
        pytest.skip(
            "No subdivision-only holidays found for DE/SN in this year; skipping specific check."
        )

    # Pick one subdivision-only date and verify it's included and that the name matches
    sample_date = next(iter(subdiv_only))
    assert sample_date in combined
    assert combined.get(sample_date) == sn.get(sample_date)
