import pytest
from datetime import datetime
from tempfile import TemporaryDirectory
from pathlib import Path
from PIL import Image

from designer.collage.CalendarGenerator import CalendarGenerator
from designer.common.Config import Config


@pytest.fixture
def sample_config():
    """Erstellt eine Beispielkonfiguration für Tests."""
    config = Config()
    config.startDate = datetime(2024, 1, 1)
    config.width = 2100  # Beispielwerte in Pixel
    config.calendarHeight = 300
    config.marginBottom = 20
    config.marginSides = 20
    config.fontSizeLarge = 40
    config.fontSizeSmall = 20
    config.fontSizeAnniversaries = 15
    config.textColor1 = (0, 0, 0)  # Schwarz
    config.textColor2 = (255, 0, 0)  # Rot
    config.holidayColor = (0, 0, 255)  # Blau
    config.backgroundColor = (255, 255, 255)  # Weiß
    config.language = "de_DE"
    return config


@pytest.fixture
def calendar_generator(sample_config):
    """Erzeugt eine Instanz von CalendarGenerator für Tests."""
    return CalendarGenerator(config=sample_config)


def test_generate_calendar(calendar_generator, sample_config):
    """Testet die Generierung eines Kalenders als Bild."""
    test_date = datetime(2024, 1, 1)
    width, height = sample_config.width, sample_config.calendarHeight

    image = calendar_generator.generateCalendar(test_date, width, height)

    assert isinstance(image, Image.Image), "Das erzeugte Objekt sollte ein PIL Image sein."
    assert image.size == (width, height), "Die Bildgröße sollte mit der Konfiguration übereinstimmen."


def test_get_cols_property(calendar_generator):
    """Testet die Berechnung der Spalten-Eigenschaften."""
    cols, col_width = calendar_generator.get_cols_property(2100)

    assert isinstance(cols, float), "Die Spaltenanzahl sollte ein Float sein."
    assert isinstance(col_width, float), "Die Spaltenbreite sollte ein Float sein."
    assert cols > 0, "Die Spaltenanzahl sollte größer als 0 sein."
    assert col_width > 0, "Die Spaltenbreite sollte größer als 0 sein."


@pytest.mark.parametrize(
    "month_no, expected_name",
    [
        (1, "Januar"),
        (2, "Februar"),
        (4, "April"),
        (12, "Dezember"),
    ],
)
def test_get_month_name(calendar_generator, month_no, expected_name):
    """Testet die korrekte Ausgabe von Monatsnamen."""
    month_name = calendar_generator.get_month_name(month_no, locale_name="de_DE.UTF-8")
    assert month_name == expected_name, f"Erwartet: {expected_name}, erhalten: {month_name}"


@pytest.mark.parametrize(
    "day_no, expected_name",
    [
        (0, "Montag"),
        (1, "Dienstag"),
        (2, "Mittwoch"),
        (6, "Sonntag"),
    ],
)
def test_get_day_name(calendar_generator, day_no, expected_name):
    """Testet die korrekte Ausgabe von Wochentagsnamen."""
    day_name = calendar_generator.get_day_name(day_no, locale_name="de_DE")
    assert day_name == expected_name, f"Erwartet: {expected_name}, erhalten: {day_name}"


def test_get_combined_holidays(calendar_generator):
    """Testet das Laden von Feiertagen."""
    year = 2024
    holidays_dict = calendar_generator.get_combined_holidays(year, country="DE", subdivs=["BY", "SN"])

    assert isinstance(holidays_dict, dict), "Feiertage sollten als Dictionary zurückgegeben werden."
    assert len(holidays_dict) > 0, "Es sollten Feiertage gefunden werden."
    assert datetime(2024, 1, 1) in holidays_dict, "Neujahr sollte enthalten sein."


def test_generate_calendar_saves_image(calendar_generator, sample_config):
    """Testet, ob das Kalenderbild korrekt gespeichert werden kann."""
    test_date = datetime(2024, 1, 1)

    with TemporaryDirectory() as temp_dir:
        output_path = Path(temp_dir) / "calendar_test.jpg"
        image = calendar_generator.generateCalendar(test_date, sample_config.width, sample_config.calendarHeight)
        image.save(output_path)

        assert output_path.exists(), "Das Bild sollte erfolgreich gespeichert werden."
