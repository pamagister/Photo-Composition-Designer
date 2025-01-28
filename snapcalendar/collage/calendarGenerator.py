import calendar
import locale
import os
from datetime import timedelta

import holidays
from PIL import Image, ImageDraw, ImageFont

from snapcalendar.common.anniversaries import Anniversaries
from snapcalendar.common.config import Config


class CalendarGenerator:
    def __init__(self, config=None, anniversaries=None):
        self.config = config or Config()
        self.anniversaries = anniversaries or Anniversaries()
        self.width = self.config.width
        self.calendarHeight = self.config.calendarHeight
        self.marginBottom = self.config.marginBottom
        self.marginSides = self.config.marginSides
        self.fontSizeLarge = self.config.fontSizeLarge
        self.fontSizeSmall = self.config.fontSizeSmall
        self.fontSizeAnniversaries = self.config.fontSizeAnniversaries
        if self.config.usePhotoLocationMaps:
            self.width -= self.calendarHeight - 2 * self.config.marginSides

    def generateCalendarium(self, date):
        year = date.year
        language = self.config.language
        # Berechne die Daten
        dates = [date + timedelta(days=i) for i in range(7)]

        # Feiertage für das Jahr und das Land abrufen
        country_code = language.split("_")[1].upper()  # z.B. "de_DE" -> "DE"

        localHolidays = self.get_combined_holidays(year, country_code, self.config.holidayCountries)

        # Erstelle das Bild
        img = Image.new("RGB", (self.width, self.calendarHeight), self.config.backgroundColor)
        draw = ImageDraw.Draw(img)

        # Lade die Schriftarten
        try:
            font_large = ImageFont.truetype("DejaVuSans.ttf", int(self.fontSizeLarge))
            font_small = ImageFont.truetype("DejaVuSansCondensed.ttf", int(self.fontSizeSmall))
            font_holiday = ImageFont.truetype("DejaVuSansCondensed.ttf", int(self.fontSizeAnniversaries))
        except:
            font_large = font_small = ImageFont.load_default()

        # Zeichne Monat und Jahr
        month_name = self.get_month_name(dates[0].month, language)
        if self.config.useShortMonthNames:
            month_name = month_name[:3]

        cols_count, col_width = self.get_cols_property()

        header_text = f"{month_name} {str(year)[-2:]}"
        base_y = self.calendarHeight - self.marginBottom - self.fontSizeLarge - self.fontSizeAnniversaries

        draw.text((self.marginSides * 3, base_y), header_text, font=font_large, fill=self.config.textColor2, anchor="la")
        spacing_date = int(self.fontSizeSmall * 0.4)
        # Zeichne Wochentage und Zahlen
        for day_no in range(7):
            x_pos = self.marginSides * 3 + (day_no + cols_count) * col_width
            day_date = dates[day_no]
            date_key = (day_date.day, day_date.month)  # (Tag, Monat)
            date = dates[day_no]
            holiday_name = localHolidays.get(date)  # Name des Feiertags ermitteln

            # Feiertage und Wochenende hervorheben
            if day_date.weekday() >= 6 or day_date in localHolidays:
                name_color = self.config.textColor2
                number_color = self.config.holidayColor
            else:
                name_color = self.config.textColor2
                number_color = self.config.textColor1

            # Wochentag und Tag
            day_name = self.get_day_name(day_no, language)
            draw.text((x_pos, base_y - spacing_date), day_name, font=font_small, fill=name_color, anchor="md")
            draw.text((x_pos, base_y), str(day_date.day), font=font_large, fill=number_color, anchor="ma")

            # Feiertage
            if holiday_name:
                draw.text(
                    (x_pos, base_y + self.fontSizeLarge + self.fontSizeAnniversaries + spacing_date),
                    holiday_name,
                    font=font_holiday,
                    fill=self.config.holidayColor,
                    anchor="md",
                )

            # Geburtstage/Todestage
            elif date_key in self.anniversaries:
                birthday_label = self.anniversaries[date_key]
                draw.text(
                    (x_pos, base_y + self.fontSizeLarge + self.fontSizeAnniversaries + spacing_date),
                    birthday_label,
                    font=font_holiday,
                    fill=self.config.textColor1,
                    anchor="md",
                )

        return img

    def get_cols_property(self):
        if self.config.useShortMonthNames:
            cols = 2.0
        else:
            cols = 4.0
        col_width = (self.width - 2 * self.config.marginSides) // (7 + cols - 0.5)
        return cols, col_width

    @staticmethod
    def get_month_name(month_no, locale_name="en_US.UTF-8"):
        try:
            locale.setlocale(locale.LC_TIME, locale_name)
            return calendar.month_name[month_no]
        except locale.Error:
            return calendar.month_name[month_no]
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
    def get_combined_holidays(year, country='EN', subdivs=None):
        """
        Kombiniert Feiertage aus mehreren Ländern oder Subdivisionen.

        Args:
            year (int): Das Jahr, für das Feiertage abgerufen werden sollen.
            country (str): Das Land z.B. EN oder DE
            countryCodes (list): Eine Liste von Länder- oder Subdivision-Codes, z. B. ['SN', 'BY'].

        Returns:
            holidays.HolidayBase: Ein Objekt mit allen kombinierten Feiertagen.
        """
        combined_holidays = holidays.HolidayBase()
        for subdiv in subdivs:

            # Lade Feiertage für das Land/Subdivision
            local_holidays = holidays.country_holidays(country, years=year, subdiv=subdiv)

            # Kombiniere mit den bisherigen Feiertagen
            combined_holidays.update(local_holidays)

        return combined_holidays


def main():
    # Config aus Datei laden
    config = Config()
    calendar_gen = CalendarGenerator(config=config)

    temp_dir = "../../tests/calendar"
    os.makedirs(temp_dir, exist_ok=True)
    startDate = config.startDate

    for week in range(40, 45):
        date = startDate + timedelta(weeks=week)
        image = calendar_gen.generateCalendarium(date)
        image_path = os.path.join(temp_dir, f"calendar_{date.year}-{date.month.zfill(2)}-{date.day.zfill(2)}.png")
        image.save(image_path)
        print(f"Generated: {image_path}")


if __name__ == "__main__":
    main()
