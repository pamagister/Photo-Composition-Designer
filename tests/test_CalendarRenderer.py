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
