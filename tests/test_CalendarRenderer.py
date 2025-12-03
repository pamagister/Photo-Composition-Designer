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
