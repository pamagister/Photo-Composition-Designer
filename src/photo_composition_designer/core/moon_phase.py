from __future__ import annotations

from datetime import datetime

from astral import moon


class MoonPhase:
    """Utility class for computing Unicode moon phase symbols."""

    DETAILED = False

    @staticmethod
    def get_moon_phase_symbol_light(d: datetime) -> str:
        """
        Return the Unicode symbol representing the Moon's illuminated
        phase for the given date.

        This method uses the actual lunar phase from Astral and maps it
        to a Unicode icon using `get_moon_symbol()`.
        """
        return MoonPhase.get_moon_symbol(moon.phase(d))

    @staticmethod
    def get_moon_phase_symbol_dark(d: datetime) -> str:
        """
        Return the Unicode symbol for the Moon as it would appear in
        an inverted-illumination (dark-mode) scheme. This is helpful
        for bright background.

        This is computed by shifting the phase forward by 14 (half a
        lunar cycle), effectively flipping the illuminated side.
        """
        return MoonPhase.get_moon_symbol((moon.phase(d) + 14) % 28)

    @staticmethod
    def get_moon_symbol(phase: float) -> str:
        """
        Map an Astral moon-phase value to a Unicode symbol.

        Parameters
        ----------
        phase : float
            The moon phase value from Astral (0–29.53 approx).

        Returns
        -------
        str
            A Unicode moon-phase emoji corresponding to the integer
            phase bucket. Only major phases are returned unless
            `DETAILED` is enabled.

        Notes
        -----
        Recognized phases:

            0   → 🌑  new moon
            4   → 🌒  waxing crescent      (detailed mode only)
            7   → 🌓  first quarter
            10  → 🌔  waxing gibbous       (detailed mode only)
            14  → 🌕  full moon
            18  → 🌖  waning gibbous       (detailed mode only)
            21  → 🌗  last quarter
            25  → 🌘  waning crescent      (detailed mode only)

        All other values return the empty string.
        """
        p = int(phase)
        if p == 0:
            return "🌑"
        if p == 4 and MoonPhase.DETAILED:
            return "🌒"
        if p == 7:
            return "🌓"
        if p == 10 and MoonPhase.DETAILED:
            return "🌔"
        if p == 14:
            return "🌕"
        if p == 18 and MoonPhase.DETAILED:
            return "🌖"
        if p == 21:
            return "🌗"
        if p == 25 and MoonPhase.DETAILED:
            return "🌘"
        return ""
