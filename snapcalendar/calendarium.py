import os
import calendar
from datetime import datetime, timedelta
import locale
from PIL import Image, ImageDraw, ImageFont

class Calendarium:
    def __init__(self, width=1920, height=200, year=2025,
                 backgroundColor=[20, 0, 0],
                 textColor1=[255, 255, 255],
                 textColor2=[150, 150, 150],
                 weekendColor=[255, 0, 0],
                 language="de_DE",
                 fontSizeLarge=0.5,
                 fontSizeSmall=0.15,
                 marginBottom=30, marginSides=10, spacing=10):
        self.width = width
        self.height = height
        self.year = year
        self.backgroundColor = tuple(backgroundColor)
        self.textColor1 = tuple(textColor1)
        self.textColor2 = tuple(textColor2)
        self.weekendColor = tuple(weekendColor)
        self.language = language
        self.fontSizeLarge = fontSizeLarge*height
        self.fontSizeSmall = fontSizeSmall*height
        self.marginBottom = marginBottom
        self.marginSides = marginSides
        self.spacing = spacing
        self.shortDayNames = True
        self.shortMonthNames = True

    def generateCalendarium(self, week):
        # Calculate the first day of the week
        first_day = datetime.strptime(f"{self.year}-W{week}-1", "%Y-W%U-%w")
        dates = [first_day + timedelta(days=i) for i in range(7)]

        # Create image
        img = Image.new("RGB", (self.width, self.height), self.backgroundColor)
        draw = ImageDraw.Draw(img)

        # Load a font (you may need to adjust the path to the font file)
        try:
            font_large = ImageFont.truetype("arial.ttf", self.fontSizeLarge)
            font_small = ImageFont.truetype("arial.ttf", self.fontSizeSmall)
        except:
            font_large = font_small = ImageFont.load_default()

        # Draw month and year in the same line as the days
        month_name = self.get_month_name(dates[0].month, self.language)
        if self.shortMonthNames:
            month_name = month_name[0:3]
            cols_month = 2.5
        else:
            cols_month = 4.5

        header_text = f"{month_name} {str(self.year)[-2:]}"

        col_width = (self.width - 2 * self.marginSides) // (7 + cols_month-0.5)
        base_y = self.height - self.marginBottom - self.fontSizeLarge

        draw.text((self.marginSides*3, base_y), header_text, font=font_large, fill=self.textColor2, anchor="la")

        # Draw weekdays and dates
        for day_no in range(7):
            x_pos = self.marginSides + (day_no + cols_month) * col_width
            day_color = self.weekendColor if day_no >= 5 else self.textColor1
            day_name = self.get_day_name(day_no, self.language)

            # Weekday name
            draw.text((x_pos, base_y - self.spacing), day_name, font=font_small, fill=self.textColor2, anchor="md")

            # Day of the month
            draw.text((x_pos, base_y), str(dates[day_no].day), font=font_large, fill=day_color, anchor="ma")

        return img

    @staticmethod
    def get_month_name(month_no, locale_name="en_US.UTF-8"):
        try:
            # Set the desired locale
            locale.setlocale(locale.LC_TIME, locale_name)
            # Get the localized month name
            return calendar.month_name[month_no]
        except locale.Error:
            # Fallback in case the locale is not supported
            return calendar.month_name[month_no]
        finally:
            # Reset to the default locale
            locale.setlocale(locale.LC_TIME, "")

    @staticmethod
    def get_day_name(day_no, locale_name="en_US.UTF-8"):
        try:
            # Set the desired locale
            locale.setlocale(locale.LC_TIME, locale_name)
            # Get the localized month name
            return calendar.day_name[day_no]
        except locale.Error:
            # Fallback in case the locale is not supported
            return calendar.day_name[day_no]
        finally:
            # Reset to the default locale
            locale.setlocale(locale.LC_TIME, "")


def main():
    # Create an instance of Calendarium
    calendar_gen = Calendarium()

    # Create a temp directory to store the images
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)

    # Generate calendaria for several weeks  to test function and design
    for week in range(34, 37):
        image = calendar_gen.generateCalendarium(week)
        image_path = os.path.join(temp_dir, f"calendarium_week_{week}.png")
        image.save(image_path)
        print(f"Generated: {image_path}")

if __name__ == "__main__":
    main()
