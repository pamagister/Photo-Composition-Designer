import os
import calendar
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

class Calendarium:
    def __init__(self, width=1920, height=300, year=2025,
                 backgroundColor=[20, 0, 0], textColor=[255, 255, 255],
                 weekendColor=[255, 0, 0], language="german"):
        self.width = width
        self.height = height
        self.year = year
        self.backgroundColor = tuple(backgroundColor)
        self.textColor = tuple(textColor)
        self.weekendColor = tuple(weekendColor)
        self.language = language

        # Set the language for weekdays
        if self.language == "german":
            self.weekdays = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
        else:
            self.weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def generateCalendarium(self, week):
        # Calculate the first day of the week
        first_day = datetime.strptime(f"{self.year}-W{week}-1", "%Y-W%U-%w")
        dates = [first_day + timedelta(days=i) for i in range(7)]

        # Create image
        img = Image.new("RGB", (self.width, self.height), self.backgroundColor)
        draw = ImageDraw.Draw(img)

        # Load a font (you may need to adjust the path to the font file)
        try:
            font_large = ImageFont.truetype("arial.ttf", 40)
            font_small = ImageFont.truetype("arial.ttf", 30)
        except:
            font_large = font_small = ImageFont.load_default()

        # Draw month and year
        month_name = calendar.month_name[dates[0].month] if self.language != "german" else calendar.month_name[dates[0].month].capitalize()
        header_text = f"{month_name} {str(self.year)[-2:]}"
        draw.text((10, 10), header_text, font=font_large, fill=self.textColor)

        # Draw weekdays and dates
        col_width = self.width // 8
        y_offset = 100
        for idx, day in enumerate(self.weekdays):
            x_pos = (idx + 1) * col_width
            day_color = self.weekendColor if idx >= 5 else self.textColor

            # Weekday name
            draw.text((x_pos, y_offset), day, font=font_small, fill=day_color, anchor="mm")

            # Day of the month
            draw.text((x_pos, y_offset + 40), str(dates[idx].day), font=font_small, fill=day_color, anchor="mm")

        return img


def main():
    # Create an instance of Calendarium
    calendar_gen = Calendarium()

    # Create a temp directory to store the images
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)

    # Generate calendaria for weeks 1-5
    for week in range(1, 6):
        image = calendar_gen.generateCalendarium(week)
        image_path = os.path.join(temp_dir, f"calendarium_week_{week}.png")
        image.save(image_path)
        print(f"Generated: {image_path}")

if __name__ == "__main__":
    main()
