import calendar
import locale
import os
from datetime import datetime, timedelta
import holidays

from PIL import Image, ImageDraw, ImageFont

from common.config import Config  # Importiere die Config-Klasse


class Calendarium:
    def __init__(self, config=None):
        self.config = config or Config()

    def generateCalendarium(self, week):
        # Nutze Parameter aus der Config
        width = self.config.width
        calendarHeight = self.config.calendarHeight
        marginBottom = self.config.marginBottom
        marginSides = self.config.marginSides
        fontSizeLarge = self.config.fontSizeLarge
        fontSizeSmall = self.config.fontSizeSmall
        fontSizeHoliday = self.config.fontSizeHoliday
        year = self.config.year
        language = self.config.language

        # Berechne die Daten
        first_day = datetime.strptime(f"{year}-W{week}-1", "%Y-W%U-%w")
        dates = [first_day + timedelta(days=i) for i in range(7)]

        # Feiertage für das Jahr und das Land abrufen
        country_code = language.split("_")[1].upper()  # z.B. "de_DE" -> "DE"

        localHolidays = self.get_combined_holidays(year, country_code, self.config.holidayCountries)

        # Erstelle das Bild
        img = Image.new("RGB", (width, calendarHeight), self.config.backgroundColor)
        draw = ImageDraw.Draw(img)

        # Lade die Schriftarten
        try:
            font_large = ImageFont.truetype("arial.ttf", int(fontSizeLarge))
            font_small = ImageFont.truetype("arial.ttf", int(fontSizeSmall))
            font_holiday = ImageFont.truetype("arial.ttf", int(fontSizeHoliday))
        except:
            font_large = font_small = ImageFont.load_default()

        # Zeichne Monat und Jahr
        month_name = self.get_month_name(dates[0].month, language)
        if self.config.shortMonthNames:
            month_name = month_name[:3]
            cols_month = 2.5
        else:
            cols_month = 4.5

        header_text = f"{month_name} {str(year)[-2:]}"
        col_width = (width - 2 * marginSides) // (7 + cols_month - 0.5)
        base_y = calendarHeight - marginBottom - fontSizeLarge - fontSizeHoliday

        draw.text((marginSides * 3, base_y), header_text, font=font_large, fill=self.config.textColor2, anchor="la")
        spacing_date =  int(fontSizeSmall * 0.4)
        # Zeichne Wochentage und Zahlen
        for day_no in range(7):
            x_pos = marginSides + (day_no + cols_month) * col_width
            day_date = dates[day_no]
            date = dates[day_no]
            holiday_name = localHolidays.get(date)  # Name des Feiertags ermitteln

            # Feiertage und Wochenende hervorheben
            if day_date.weekday() >= 5 or day_date in localHolidays:
                day_color = self.config.holidayColor
            else:
                day_color = self.config.textColor1

            # Wochentag und Tag
            day_name = self.get_day_name(day_no, language)
            draw.text((x_pos, base_y - spacing_date), day_name, font=font_small, fill=self.config.textColor2, anchor="md")
            draw.text((x_pos, base_y), str(day_date.day), font=font_large, fill=day_color, anchor="ma")
            if holiday_name:
                draw.text((x_pos, base_y+fontSizeLarge+fontSizeHoliday+spacing_date), holiday_name, font=font_holiday, fill=self.config.holidayColor, anchor="md")

        return img

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

    def get_combined_holidays(self, year, country='EN', subdivs = None):
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
    config = Config("config.ini")
    calendar_gen = Calendarium(config=config)

    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)

    for week in range(42, 47):
        image = calendar_gen.generateCalendarium(week)
        image_path = os.path.join(temp_dir, f"calendarium_week_{week}.png")
        image.save(image_path)
        print(f"Generated: {image_path}")


if __name__ == "__main__":
    main()
