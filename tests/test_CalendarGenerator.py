from pathlib import Path

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.image.CalendarGenerator import (
    create_calendar_generator_from_config,
)


def test_CalendarGenerator_proper_name():
    # Create temp directory
    project_root = Path(__file__).resolve().parents[1]
    temp_dir = project_root / "temp"
    temp_dir.mkdir(exist_ok=True)

    # Load default config
    config = ConfigParameterManager()

    # Build generator from config
    cg = create_calendar_generator_from_config(config)

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
    cal_img = cg.generate_calendar(
        dt,
        width=config.size.width.value * config.size.dpi.value / 25.4,
        height=config.size.calendarHeight.value * config.size.dpi.value / 25.4,
    )
    cal_path = temp_dir / "week_test.jpg"
    cal_img.save(cal_path)

    assert cal_path.exists()
    assert cal_path.stat().st_size > 0

    print("Generated files:", title_path, cal_path)
