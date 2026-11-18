from datetime import datetime

import pytest

# Monkeypatch target for astral.moon.phase
import photo_composition_designer.core.moon_phase as mpModule
from photo_composition_designer.core.moon_phase import MoonPhase

# --- Helpers ---------------------------------------------------------------


class DummyMoon:
    """Simple stubs to bypass Astral and supply specific phases."""

    def __init__(self, phase):
        self.phase_value = phase

    def phase(self, d):
        return self.phase_value


# --- Tests ----------------------------------------------------------------


@pytest.mark.parametrize(
    "phase, expected",
    [
        (0, "🌑"),  # new moon
        (7, "🌓"),  # first quarter
        (14, "🌕"),  # full moon
        (21, "🌗"),  # last quarter
    ],
)
def test_light_mode_major_phases(monkeypatch, phase, expected):
    """Test that major phases map correctly in non-detailed mode."""
    # Disable detailed mode
    MoonPhase.DETAILED = False

    dummy = DummyMoon(phase)
    monkeypatch.setattr(mpModule.moon, "phase", dummy.phase)

    symbol = MoonPhase.get_moon_phase_symbol_light(datetime.now())
    assert symbol == expected


@pytest.mark.parametrize("phase", [4, 10, 18, 25])
def test_light_mode_minor_phases_not_detailed(monkeypatch, phase):
    """Minor phases should return empty string unless detailed mode is on."""
    MoonPhase.DETAILED = False

    dummy = DummyMoon(phase)
    monkeypatch.setattr(mpModule.moon, "phase", dummy.phase)

    symbol = MoonPhase.get_moon_phase_symbol_light(datetime.now())
    assert symbol == ""


@pytest.mark.parametrize(
    "phase, expected",
    [
        (4, "🌒"),
        (10, "🌔"),
        (18, "🌖"),
        (25, "🌘"),
    ],
)
def test_light_mode_minor_phases_detailed(monkeypatch, phase, expected):
    """Minor phases should map correctly when detailed mode is enabled."""
    MoonPhase.DETAILED = True

    dummy = DummyMoon(phase)
    monkeypatch.setattr(mpModule.moon, "phase", dummy.phase)

    symbol = MoonPhase.get_moon_phase_symbol_light(datetime.now())
    assert symbol == expected


def test_dark_mode_phase_shift(monkeypatch):
    """
    Dark mode adds +14 and mod 28.
    Example:
        input: 0 (new moon)
        dark-mode: (0 + 14) % 28 = 14 → full moon
    """
    MoonPhase.DETAILED = False

    dummy = DummyMoon(0)
    monkeypatch.setattr(mpModule.moon, "phase", dummy.phase)

    symbol = MoonPhase.get_moon_phase_symbol_dark(datetime.now())
    assert symbol == "🌕"  # shifted to full moon


@pytest.mark.parametrize(
    "phase, expected",
    [
        (14, "🌑"),  # full → new (inversion)
        (7, "🌗"),  # first quarter → last quarter
        (21, "🌓"),  # last quarter → first quarter
    ],
)
def test_dark_mode_other_shifts(monkeypatch, phase, expected):
    """Verify additional inverted pairs."""
    MoonPhase.DETAILED = False

    dummy = DummyMoon(phase)
    monkeypatch.setattr(mpModule.moon, "phase", dummy.phase)

    symbol = MoonPhase.get_moon_phase_symbol_dark(datetime.now())
    assert symbol == expected


def test_unrecognized_phase_returns_empty(monkeypatch):
    """Phases not matched explicitly must return empty string."""
    MoonPhase.DETAILED = True  # mode doesn't matter here

    dummy = DummyMoon(3)  # not a recognized integer
    monkeypatch.setattr(mpModule.moon, "phase", dummy.phase)

    symbol = MoonPhase.get_moon_phase_symbol_light(datetime.now())
    assert symbol == ""
