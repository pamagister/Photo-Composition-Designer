import os
import random

from PIL import Image

from calendarium import Calendarium
from common.config import Config


class CollageGenerator:
    def __init__(self, config=None):
        self.config = config or Config()
        self.calendarium_height = self.config.calendarHeight
        self.width = self.config.width
        self.height = self.config.height
        self.spacing = self.config.spacing

    def crop_and_resize(self, image, target_width, target_height):
        """
        Schneidet ein Bild proportional zu und skaliert es dann auf die gewünschte Größe.

        :param image: PIL.Image-Objekt
        :param target_width: Zielbreite
        :param target_height: Zielhöhe
        :return: Proportionell beschnittenes und skaliertes Bild
        """
        img_width, img_height = image.size
        aspect_ratio_img = img_width / img_height
        aspect_ratio_target = target_width / target_height

        if aspect_ratio_img > aspect_ratio_target:
            # Bild ist breiter -> Seitlich beschneiden
            new_width = int(aspect_ratio_target * img_height)
            left = (img_width - new_width) // 2
            right = left + new_width
            cropped = image.crop((left, 0, right, img_height))
        else:
            # Bild ist höher -> Oben und unten beschneiden
            new_height = int(img_width / aspect_ratio_target)
            top = (img_height - new_height) // 2
            bottom = top + new_height
            cropped = image.crop((0, top, img_width, bottom))

        return cropped.resize((target_width, target_height))

    def generate_collage(self, image_files, week, output_path):
        """
        Erzeugt eine Collage mit Bildern und einem Calendarium.

        :param image_files: Liste von Bilddateipfaden
        :param week: Wochennummer
        :param output_path: Pfad zur gespeicherten Collage
        """
        # Canvas erstellen
        collage = Image.new("RGB", (self.width, self.height), self.config.backgroundColor)

        # Calendarium generieren
        calendarium = Calendarium(self.config).generateCalendarium(week)
        collage.paste(calendarium, (0, self.height - self.calendarium_height))

        # Platz für Bilder berechnen
        available_height = self.height - self.calendarium_height - self.spacing
        available_width = self.width

        if len(image_files) == 0:
            print(f"Keine Bilder für Woche {week}.")
            return

        images = [Image.open(img) for img in image_files]

        # Anordnungslogik basierend auf Bildanzahl
        if len(images) == 1:
            # Ein Bild -> Mitte der Fläche
            img = self.crop_and_resize(images[0], available_width, available_height)
            collage.paste(img, (0, 0))

        elif len(images) == 2:
            # Zwei Bilder -> Links/Rechts gleich aufteilen
            half_width = (available_width - self.spacing) // 2
            img1 = self.crop_and_resize(images[0], half_width, available_height)
            img2 = self.crop_and_resize(images[1], half_width, available_height)
            collage.paste(img1, (0, 0))
            collage.paste(img2, (half_width + self.spacing, 0))

        elif len(images) == 3:
            # Drei Bilder -> Ein großes Bild links/rechts, zwei kleinere übereinander
            large_width = int(available_width * 0.6)
            small_width = available_width - large_width - self.spacing
            small_height = (available_height - self.spacing) // 2

            img1 = self.crop_and_resize(images[0], large_width, available_height)
            img2 = self.crop_and_resize(images[1], small_width, small_height)
            img3 = self.crop_and_resize(images[2], small_width, small_height)

            if random.choice([True, False]):
                # Großes Bild links
                collage.paste(img1, (0, 0))
                collage.paste(img2, (large_width + self.spacing, 0))
                collage.paste(img3, (large_width + self.spacing, small_height + self.spacing))
            else:
                # Großes Bild rechts
                collage.paste(img1, (small_width + self.spacing, 0))
                collage.paste(img2, (0, 0))
                collage.paste(img3, (0, small_height + self.spacing))

        elif len(images) == 4:
            # Vier Bilder -> Goldener Schnitt mit zwei kleinen und zwei großen Bildern
            small_width = int(available_width * 0.4)
            large_width = available_width - small_width - self.spacing
            small_height = int(available_height * 0.4)
            large_height = available_height - small_height - self.spacing

            img1 = self.crop_and_resize(images[0], small_width, small_height)
            img2 = self.crop_and_resize(images[1], large_width, large_height)
            img3 = self.crop_and_resize(images[2], large_width, small_height)
            img4 = self.crop_and_resize(images[3], small_width, large_height)

            collage.paste(img1, (0, 0))
            collage.paste(img2, (small_width + self.spacing, 0))
            collage.paste(img3, (small_width + self.spacing, large_height + self.spacing))
            collage.paste(img4, (0, small_height + self.spacing))

        else:
            # Mehr als vier Bilder -> Raster basierend auf Anzahl
            cols = int(len(images) ** 0.5)
            rows = (len(images) + cols - 1) // cols
            cell_width = (available_width - (cols - 1) * self.spacing) // cols
            cell_height = (available_height - (rows - 1) * self.spacing) // rows

            for i, img in enumerate(images):
                row = i // cols
                col = i % cols
                resized_img = self.crop_and_resize(img, cell_width, cell_height)
                x_offset = col * (cell_width + self.spacing)
                y_offset = row * (cell_height + self.spacing)
                collage.paste(resized_img, (x_offset, y_offset))

        # Collage speichern
        collage.save(output_path)
        print(f"Collage gespeichert: {output_path}")


def main():
    """
    Testfunktion: Generiert Collagen für alle Wochen aus dem Ordner ../res/images.
    """
    base_dir = "../res/images"
    output_dir = "output/collages"
    os.makedirs(output_dir, exist_ok=True)

    for week_folder in sorted(os.listdir(base_dir)):
        week_path = os.path.join(base_dir, week_folder)
        if os.path.isdir(week_path) and week_folder.startswith("week_"):
            week_number = int(week_folder.split("_")[1])  # Extrahiere Wochennummer
            image_files = [
                os.path.join(week_path, file)
                for file in sorted(os.listdir(week_path))
                if file.lower().endswith((".png", ".jpg", ".jpeg"))
            ]

            if not image_files:
                print(f"Keine Bilder in {week_folder} gefunden, überspringe...")
                continue

            # Collage generieren
            output_path = os.path.join(output_dir, f"collage_week_{week_number}.jpg")
            CollageGenerator().generate_collage(image_files, week_number, output_path)


if __name__ == "__main__":
    main()
