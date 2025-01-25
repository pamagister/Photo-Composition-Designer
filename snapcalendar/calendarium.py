import os
import calendar
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from common.config import Config  # Importiere die Config-Klasse
import locale

class Calendarium:
    def __init__(self, config=None):
        # Falls keine Konfiguration übergeben wird, nutze die Standardkonfiguration
        self.config = config or Config()

    def generateCalendarium(self, week):
        # Nutze Parameter aus der Config
        width = self.config.width
        height = self.config.height
        marginBottom = self.config.marginBottom
        marginSides = self.config.marginSides
        fontSizeLarge = self.config.fontSizeLarge
        fontSizeSmall = self.config.fontSizeSmall

        # Berechne die Daten
        first_day = datetime.strptime(f"{self.config.year}-W{week}-1", "%Y-W%U-%w")
        dates = [first_day + timedelta(days=i) for i in range(7)]

        # Erstelle das Bild
        img = Image.new("RGB", (width, height), self.config.backgroundColor)
        draw = ImageDraw.Draw(img)

        # Lade die Schriftarten
        try:
            font_large = ImageFont.truetype("arial.ttf", int(fontSizeLarge))
            font_small = ImageFont.truetype("arial.ttf", int(fontSizeSmall))
        except:
            font_large = font_small = ImageFont.load_default()

        # Zeichne Monat und Jahr
        month_name = self.get_month_name(dates[0].month, self.config.language)
        if self.config.shortMonthNames:
            month_name = month_name[:3]
            cols_month = 2.5
        else:
            cols_month = 4.5

        header_text = f"{month_name} {str(self.config.year)[-2:]}"
        col_width = (width - 2 * marginSides) // (7 + cols_month - 0.5)
        base_y = height - marginBottom - fontSizeLarge

        draw.text((marginSides * 3, base_y), header_text, font=font_large, fill=self.config.textColor2, anchor="la")

        # Zeichne Wochentage und Zahlen
        for day_no in range(7):
            x_pos = marginSides + (day_no + cols_month) * col_width
            day_color = self.config.weekendColor if day_no >= 5 else self.config.textColor1
            day_name = self.get_day_name(day_no, self.config.language)

            draw.text((x_pos, base_y - self.config.spacing), day_name, font=font_small, fill=self.config.textColor2, anchor="md")
            draw.text((x_pos, base_y), str(dates[day_no].day), font=font_large, fill=day_color, anchor="ma")

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

def main():
    # Config aus Datei laden
    config = Config("config.ini")
    calendar_gen = Calendarium(config=config)

    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)

    for week in range(34, 37):
        image = calendar_gen.generateCalendarium(week)
        image_path = os.path.join(temp_dir, f"calendarium_week_{week}.png")
        image.save(image_path)
        print(f"Generated: {image_path}")

if __name__ == "__main__":
    main()
