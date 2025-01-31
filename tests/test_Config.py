import pytest
from pathlib import Path
from configparser import ConfigParser
from designer.common.Config import Config


def create_temp_config_file(tmp_path, content):
    """Hilfsfunktion zum Erstellen einer temporären Konfigurationsdatei."""
    temp_file = tmp_path / "test_config.ini"
    temp_file.write_text(content, encoding="utf-8")
    return temp_file


class TestConfig:
    def test_write_config(self, tmp_path):
        """Testet, ob die Standardwerte korrekt in eine Datei geschrieben werden."""
        temp_config_file = tmp_path / "config_output.ini"
        cfg = Config()
        cfg.write_config(temp_config_file)

        # Original-Datei als Referenz einlesen
        project_base_path = Path(__file__).parent.parent
        original_config_file = project_base_path / "designer/config/config.ini"
        assert original_config_file.exists(), "Referenz-Konfigurationsdatei fehlt!"

        with (
            open(original_config_file, "r", encoding="utf-8") as orig,
            open(temp_config_file, "r", encoding="utf-8") as temp,
        ):
            assert orig.read() == temp.read(), "Die erzeugte Konfigurationsdatei stimmt nicht mit dem Original überein!"

    def test_read_and_update_config(self, tmp_path):
        """Testet das Einlesen einer Konfigurationsdatei mit veränderten Werten."""
        config_content = """
            [GENERAL]
            photoDirectory = ../../images
            anniversariesConfig = anniversaries_private.ini
            locationsConfig = locations_en.ini
            
            [CALENDAR]
            useCalendar = False
            language = de_DE
            """
        temp_config_file = create_temp_config_file(tmp_path, config_content)
        cfg = Config(temp_config_file)

        # Überprüfung von Standard- und aktualisierten Werten
        assert cfg.photoDirectory == Path("../../images").resolve(), "photoDirectory sollte nicht geändert sein."
        assert (
            cfg.anniversariesConfig == Path("anniversaries_private.ini").resolve()
        ), "anniversariesConfig wurde nicht aktualisiert."
        assert cfg.language == "de_DE", "Sprache sollte auf de_DE geändert sein."
        assert cfg.useCalendar is False, "useCalendar sollte auf False gesetzt sein."
