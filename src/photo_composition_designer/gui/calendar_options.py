"""Curated locale and holiday subdivision choices for project settings."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HolidaySubdivision:
    """One selectable holiday subdivision code and its display label."""

    code: str
    label: str


@dataclass(frozen=True)
class CalendarLanguage:
    """A calendar locale and the holiday subdivisions that belong to it."""

    code: str
    label: str
    country: str
    subdivisions: tuple[HolidaySubdivision, ...] = ()
    note: str = ""


_GERMAN_STATES = (
    HolidaySubdivision("BW", "Baden-Württemberg"),
    HolidaySubdivision("BY", "Bayern"),
    HolidaySubdivision("BE", "Berlin"),
    HolidaySubdivision("BB", "Brandenburg"),
    HolidaySubdivision("HB", "Bremen"),
    HolidaySubdivision("HH", "Hamburg"),
    HolidaySubdivision("HE", "Hessen"),
    HolidaySubdivision("MV", "Mecklenburg-Vorpommern"),
    HolidaySubdivision("NI", "Niedersachsen"),
    HolidaySubdivision("NW", "Nordrhein-Westfalen"),
    HolidaySubdivision("RP", "Rheinland-Pfalz"),
    HolidaySubdivision("SL", "Saarland"),
    HolidaySubdivision("SN", "Sachsen"),
    HolidaySubdivision("ST", "Sachsen-Anhalt"),
    HolidaySubdivision("SH", "Schleswig-Holstein"),
    HolidaySubdivision("TH", "Thüringen"),
)

_AUSTRIAN_STATES = (
    HolidaySubdivision("1", "Burgenland"),
    HolidaySubdivision("2", "Kärnten"),
    HolidaySubdivision("3", "Niederösterreich"),
    HolidaySubdivision("4", "Oberösterreich"),
    HolidaySubdivision("5", "Salzburg"),
    HolidaySubdivision("6", "Steiermark"),
    HolidaySubdivision("7", "Tirol"),
    HolidaySubdivision("8", "Vorarlberg"),
    HolidaySubdivision("9", "Wien"),
)

_US_STATES = (
    HolidaySubdivision("AL", "Alabama"),
    HolidaySubdivision("AK", "Alaska"),
    HolidaySubdivision("AZ", "Arizona"),
    HolidaySubdivision("AR", "Arkansas"),
    HolidaySubdivision("CA", "California"),
    HolidaySubdivision("CO", "Colorado"),
    HolidaySubdivision("CT", "Connecticut"),
    HolidaySubdivision("DE", "Delaware"),
    HolidaySubdivision("DC", "District of Columbia"),
    HolidaySubdivision("FL", "Florida"),
    HolidaySubdivision("GA", "Georgia"),
    HolidaySubdivision("HI", "Hawaii"),
    HolidaySubdivision("ID", "Idaho"),
    HolidaySubdivision("IL", "Illinois"),
    HolidaySubdivision("IN", "Indiana"),
    HolidaySubdivision("IA", "Iowa"),
    HolidaySubdivision("KS", "Kansas"),
    HolidaySubdivision("KY", "Kentucky"),
    HolidaySubdivision("LA", "Louisiana"),
    HolidaySubdivision("ME", "Maine"),
    HolidaySubdivision("MD", "Maryland"),
    HolidaySubdivision("MA", "Massachusetts"),
    HolidaySubdivision("MI", "Michigan"),
    HolidaySubdivision("MN", "Minnesota"),
    HolidaySubdivision("MS", "Mississippi"),
    HolidaySubdivision("MO", "Missouri"),
    HolidaySubdivision("MT", "Montana"),
    HolidaySubdivision("NE", "Nebraska"),
    HolidaySubdivision("NV", "Nevada"),
    HolidaySubdivision("NH", "New Hampshire"),
    HolidaySubdivision("NJ", "New Jersey"),
    HolidaySubdivision("NM", "New Mexico"),
    HolidaySubdivision("NY", "New York"),
    HolidaySubdivision("NC", "North Carolina"),
    HolidaySubdivision("ND", "North Dakota"),
    HolidaySubdivision("OH", "Ohio"),
    HolidaySubdivision("OK", "Oklahoma"),
    HolidaySubdivision("OR", "Oregon"),
    HolidaySubdivision("PA", "Pennsylvania"),
    HolidaySubdivision("RI", "Rhode Island"),
    HolidaySubdivision("SC", "South Carolina"),
    HolidaySubdivision("SD", "South Dakota"),
    HolidaySubdivision("TN", "Tennessee"),
    HolidaySubdivision("TX", "Texas"),
    HolidaySubdivision("UT", "Utah"),
    HolidaySubdivision("VT", "Vermont"),
    HolidaySubdivision("VA", "Virginia"),
    HolidaySubdivision("WA", "Washington"),
    HolidaySubdivision("WV", "West Virginia"),
    HolidaySubdivision("WI", "Wisconsin"),
    HolidaySubdivision("WY", "Wyoming"),
)

_FRENCH_REGIONS = (
    HolidaySubdivision("57", "Alsace-Moselle"),
    HolidaySubdivision("6AE", "Collectivité européenne d'Alsace"),
    HolidaySubdivision("971", "Guadeloupe"),
    HolidaySubdivision("972", "Martinique"),
    HolidaySubdivision("973", "Guyane"),
    HolidaySubdivision("974", "La Réunion"),
    HolidaySubdivision("976", "Mayotte"),
    HolidaySubdivision("BL", "Saint-Barthélemy"),
    HolidaySubdivision("MF", "Saint-Martin"),
    HolidaySubdivision("NC", "Nouvelle-Calédonie"),
    HolidaySubdivision("PF", "Polynésie française"),
    HolidaySubdivision("PM", "Saint-Pierre-et-Miquelon"),
    HolidaySubdivision("TF", "Terres australes et antarctiques françaises"),
    HolidaySubdivision("WF", "Wallis-et-Futuna"),
)

_SPANISH_REGIONS = (
    HolidaySubdivision("AN", "Andalucía"),
    HolidaySubdivision("AR", "Aragón"),
    HolidaySubdivision("AS", "Principado de Asturias"),
    HolidaySubdivision("CB", "Cantabria"),
    HolidaySubdivision("CL", "Castilla y León"),
    HolidaySubdivision("CM", "Castilla-La Mancha"),
    HolidaySubdivision("CN", "Canarias"),
    HolidaySubdivision("CT", "Cataluña"),
    HolidaySubdivision("EX", "Extremadura"),
    HolidaySubdivision("GA", "Galicia"),
    HolidaySubdivision("IB", "Illes Balears"),
    HolidaySubdivision("MC", "Región de Murcia"),
    HolidaySubdivision("MD", "Comunidad de Madrid"),
    HolidaySubdivision("NC", "Comunidad Foral de Navarra"),
    HolidaySubdivision("PV", "País Vasco"),
    HolidaySubdivision("RI", "La Rioja"),
    HolidaySubdivision("CE", "Ceuta"),
    HolidaySubdivision("ML", "Melilla"),
    HolidaySubdivision("VC", "Comunitat Valenciana"),
)

_CALENDAR_LANGUAGES = (
    CalendarLanguage("de_DE", "Deutsch (Deutschland)", "DE", _GERMAN_STATES),
    CalendarLanguage("de_AT", "Deutsch (Österreich)", "AT", _AUSTRIAN_STATES),
    CalendarLanguage("en_US", "English (United States)", "US", _US_STATES),
    CalendarLanguage("fr_FR", "Français (France)", "FR", _FRENCH_REGIONS),
    CalendarLanguage("es_ES", "Español (España)", "ES", _SPANISH_REGIONS),
    CalendarLanguage(
        "it_IT",
        "Italiano (Italia)",
        "IT",
        note="Italy uses nationwide holidays.",
    ),
)


def calendar_language_options() -> tuple[CalendarLanguage, ...]:
    """Return the supported calendar locales in display order."""
    return _CALENDAR_LANGUAGES


__all__ = [
    "CalendarLanguage",
    "HolidaySubdivision",
    "calendar_language_options",
]
