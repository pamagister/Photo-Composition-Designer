import calendar
import locale
import logging
import os
from datetime import timedelta

import holidays
import pytz
from PIL import Image, ImageDraw, ImageFont
from astral import LocationInfo, moon
from astral.sun import sun

from designer.common.Anniversaries import Anniversaries
from designer.common.Config import Config


class CalendarGenerator:
    def __init__(self, config=None):
        self.config = config or Config()
        self.anniversaries = Anniversaries(self.config.anniversariesConfig)
        self.marginSides = self.config.marginSides
        self.fontSizeLarge = self.config.fontSizeLarge
        self.fontSizeSmall = self.config.fontSizeSmall
        self.fontSizeAnniversaries = self.config.fontSizeAnniversaries

        # Retrieve public holidays for the year and the country
        year = self.config.startDate.year
        country_code = self.config.language.split("_")[1].upper()  # z.B. "de_DE" -> "DE"
        self.localHolidays = self.get_combined_holidays(year, country_code, self.config.holidayCountries)

    def generateCalendar(self, date, width, height):
        year = date.year
        language = self.config.language
        # Berechne die Daten
        dates = [date + timedelta(days=i) for i in range(7)]

        # Erstelle das Bild
        img = Image.new("RGB", (width, height), self.config.backgroundColor)
        draw = ImageDraw.Draw(img)

        # Lade die Schriftarten
        font_large = self.get_font("DejaVuSans.ttf", int(self.fontSizeLarge))
        font_small = self.get_font("DejaVuSansCondensed.ttf", int(self.fontSizeSmall))
        font_holiday = self.get_font("DejaVuSansCondensed.ttf", int(self.fontSizeAnniversaries))

        # Draw the month and year
        month_name = self.get_month_name(dates[0].month, language, abbreviation=self.config.useShortMonthNames)

        cols_count, col_width = self.get_cols_property(width)
        header_text = f"{month_name} {str(year)[-2:]}"

        draw.text(
            (0, height - self.fontSizeAnniversaries),
            header_text,
            font=font_large,
            fill=self.config.textColor2,
            anchor="ld",
        )

        # Sunrise and sunset
        timezone = "Europe/Berlin"
        location = LocationInfo("Dresden", timezone=timezone, latitude=51.0504, longitude=13.7373)

        sun_times = sun(location.observer, date=date)
        tz = pytz.timezone(timezone)

        # Convert times to local time
        sunrise_local = sun_times["sunrise"].astimezone(tz)
        sunset_local = sun_times["sunset"].astimezone(tz)

        # Output with correct time zone
        calendar_week = date.isocalendar().week
        sun_string = (
            f"KW {calendar_week}  ● ↑: {sunrise_local.strftime('%H:%M')}  ○ ↓: {sunset_local.strftime('%H:%M')}"
        )
        draw.text(
            (0, height),
            sun_string,
            font=font_holiday,
            fill=self.config.textColor2,
            anchor="ld",
        )

        # Draw days of the week and numbers
        for day_no in range(7):
            x_pos = self.marginSides + (day_no + cols_count + 0.5) * col_width
            day_date = dates[day_no]
            date_key = (day_date.day, day_date.month)  # (Tag, Monat)
            date = dates[day_no]
            holiday_name = self.localHolidays.get(date)  # Name des Feiertags ermitteln

            # Highlight holidays and weekends
            if day_date.weekday() >= 6 or day_date in self.localHolidays:
                name_color = self.config.textColor2
                number_color = self.config.holidayColor
            else:
                name_color = self.config.textColor2
                number_color = self.config.textColor1

            # Weekday and day
            day_name = self.get_day_name(day_no, language)
            if self.config.useShortDayNames:
                day_name = day_name[:2]

            # Moon phase
            moon_symbol = self.get_moon_phase_symbol(day_date)
            if moon_symbol:
                day_name = f"   {day_name} {moon_symbol}"

            draw.text(
                (x_pos, height - self.fontSizeAnniversaries - self.fontSizeLarge * 1.15),
                day_name,
                font=font_small,
                fill=name_color,
                anchor="md",
            )
            draw.text(
                (x_pos, height - self.fontSizeAnniversaries),
                str(day_date.day),
                font=font_large,
                fill=number_color,
                anchor="md",
            )

            # Birthdays/Days of death
            if date_key in self.anniversaries:
                birthday_label = self.anniversaries[date_key]
                if holiday_name:
                    birthday_label += f", {holiday_name}"  # add holiday name because it would not be printed otherwise
                draw.text(
                    (x_pos, height),
                    birthday_label,
                    font=font_holiday,
                    fill=self.config.textColor1,
                    anchor="md",
                )
            # Holidays
            elif holiday_name:
                draw.text(
                    (x_pos, height),
                    holiday_name,
                    font=font_holiday,
                    fill=self.config.holidayColor,
                    anchor="md",
                )

        return img

    def generateTitle(self, title_text, width, height):
        # Erstelle das Bild
        img = Image.new("RGB", (width, height), self.config.backgroundColor)
        draw = ImageDraw.Draw(img)
        font_large = self.get_font("DejaVuSans.ttf", int(self.fontSizeLarge))
        base_y = height - self.fontSizeAnniversaries
        draw.text((int(width / 2), base_y), title_text, font=font_large, fill=self.config.textColor1, anchor="md")

        return img

    @staticmethod
    def get_moon_phase_symbol(date):
        moon_phase = moon.phase(date)

        if moon_phase <= 1:  # Neumond
            return "○"
        elif 7.5 <= moon_phase <= 8.5:  # Zunehmender Halbmond
            return "🌗"
        elif 13.5 <= moon_phase <= 14.5:  # Vollmond
            return "●"
        elif 20.5 <= moon_phase <= 21.5:  # Abnehmender Halbmond
            return "🌓"
        else:
            return ""  # Keine spezielle Phase anzeigen

    @staticmethod
    def get_font(font_type: str = "DejaVuSans.ttf", font_size: int = 12):
        """
        Load font. Fallback to system default font
        """
        font = None
        try:
            font = ImageFont.truetype(font_type, font_size)
        except FileNotFoundError as e:
            print(f"Font file not found: {e}")
        except IOError as e:
            print(f"Unable to read font file: {e}")
        except ValueError as e:
            print(f"Invalid font size: {e}")
        except AttributeError as e:
            print(f"Missing attribute: {e}")
        except TypeError as e:
            print(f"Invalid type for font size: {e}")
        except ImportError as e:
            print(f"Pillow library not installed or imported correctly: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
        finally:
            if not font:
                font = ImageFont.load_default()
        return font

    def get_cols_property(self, width):
        if self.config.useShortMonthNames:
            cols_month_name = 1.5
        else:
            cols_month_name = 4.0
        col_width = (width - 3 * self.config.marginSides) // (7.0 + cols_month_name)
        return cols_month_name, col_width

    @staticmethod
    def get_month_name(month_no, locale_name="en_US.UTF-8", abbreviation=False):
        try:
            locale.setlocale(locale.LC_TIME, locale_name)
            return calendar.month_abbr[month_no] if abbreviation else calendar.month_name[month_no]
        except locale.Error:
            return calendar.month_abbr[month_no] if abbreviation else calendar.month_name[month_no]
        finally:
            locale.setlocale(locale.LC_TIME, "")

    @staticmethod
    def get_day_name(day_no, locale_name="en_US.UTF-8"):
        try:
            locale.setlocale(locale.LC_TIME, locale_name)
            return calendar.day_name[day_no]
        except locale.Error:
            return calendar.day_name[day_no]
        finally:
            locale.setlocale(locale.LC_TIME, "")

    @staticmethod
    def get_combined_holidays(year, country="EN", subdivs=None):
        """
        Combines holidays from several countries or subdivisions.

        Args:
            year (int): The year for which public holidays are to be retrieved.
            country (str): The country e.g. EN or DE
            subdivs (list): A list of country or subdivision codes, e.g. ['SN', 'BY'].

        Returns:
            holidays.HolidayBase: An object with all combined holidays.
        """
        years = (year, year + 1)
        combined_holidays = holidays.HolidayBase()
        combined_holidays.update(holidays.country_holidays(country, years=years))
        try:
            for subdiv in subdivs:
                # Loading holidays for the country/subdivision
                local_holidays = holidays.country_holidays(country, years=years, subdiv=subdiv)
                # Combine with the previous holidays
                combined_holidays.update(local_holidays)
        except Exception as err:
            logging.warning(f'Unable to determine holidays for country "{country}" in region "{subdiv}": {err}')

        return combined_holidays


def main():
    # Config aus Datei laden
    config = Config()
    calendar_gen = CalendarGenerator(config=config)

    temp_dir = "../../collages/calendar"
    os.makedirs(temp_dir, exist_ok=True)
    startDate = config.startDate
    first_collage = True
    title = "This is the title of the composition 2025"
    for week in range(0, 52):
        date = startDate + timedelta(weeks=week)
        if first_collage:
            image = calendar_gen.generateTitle(title, width=config.width, height=config.calendarHeight)
            first_collage = False
        else:
            image = calendar_gen.generateCalendar(date, width=config.width, height=config.calendarHeight)
        image_path = os.path.join(
            temp_dir, f"calendar_{date.year}-{str(date.month).zfill(2)}-{str(date.day).zfill(2)}.jpg"
        )
        image.save(image_path)
        print(f"Generated: {image_path}")


if __name__ == "__main__":
    main()
