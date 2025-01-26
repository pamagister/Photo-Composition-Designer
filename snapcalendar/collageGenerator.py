import os

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

    def analyze_images(self, images):
        """
        Analysiert, ob Bilder Hoch- oder Querformat haben.
        """
        analysis = []
        for img in images:
            width, height = img.size
            if height > width:
                analysis.append("portrait")
            else:
                analysis.append("landscape")
        return analysis

    def sort_by_aspect_ratio(self, images):
        """
        Sortiert Bilder basierend auf ihrem Seitenverhältnis (Breite / Höhe).
        Schmalste ("portrait") zuerst, breiteste ("landscape") zuletzt.
        """
        return sorted(images, key=lambda img: img.size[0] / img.size[1], reverse=False)

    def generate_collage(self, image_files, week, output_path):
        """
        Erzeugt eine Collage mit Bildern und einem Calendarium.
        """
        collage = Image.new("RGB", (self.width, self.height), self.config.backgroundColor)
        calendarium = Calendarium(self.config).generateCalendarium(week)
        collage.paste(calendarium, (0, self.height - self.calendarium_height))

        available_height = self.height - self.calendarium_height
        available_width = self.width

        if len(image_files) == 0:
            print(f"Keine Bilder gefunden.")
            return

        images = [Image.open(img) for img in image_files]
        # Bilder nach Seitenverhältnis sortieren
        images = self.sort_by_aspect_ratio(images)
        formats = self.analyze_images(images)

        # Anordnungslogik basierend auf Bildanzahl
        if len(images) == 1:
            self.arrange_one_image(collage, images[0], available_width, available_height)
        elif len(images) == 2:
            self.arrange_two_images(collage, images, formats, available_width, available_height)
        elif len(images) == 3:
            self.arrange_three_images(collage, images, formats, available_width, available_height)
        elif len(images) == 4:
            self.arrange_four_images(collage, images, formats, available_width, available_height)
        else:
            self.arrange_multiple_images(collage, images, available_width, available_height)

        collage.save(output_path)
        print(f"Collage gespeichert: {output_path}")

    def arrange_one_image(self, collage, image, width, height):
        """
        Layout für ein einzelnes Bild.
        """
        img = self.crop_and_resize(image, width, height)
        collage.paste(img, (0, 0))

    def arrange_two_images(self, collage, images, formats, width, height):
        """
        Layout für zwei Bilder.
        """
        if "portrait" in formats:
            portrait_idx = formats.index("portrait")
            landscape_idx = 1 - portrait_idx
            # Goldener Schnitt Layout
            portrait_width = int(width * 0.4)
            landscape_width = width - portrait_width - self.spacing
            img1 = self.crop_and_resize(images[portrait_idx], portrait_width, height)
            img2 = self.crop_and_resize(images[landscape_idx], landscape_width, height)
            collage.paste(img1, (0, 0))
            collage.paste(img2, (portrait_width + self.spacing, 0))
        else:
            # Beide Querformat -> nebeneinander
            img_width = (width - self.spacing) // 2
            img1 = self.crop_and_resize(images[0], img_width, height)
            img2 = self.crop_and_resize(images[1], img_width, height)
            collage.paste(img1, (0, 0))
            collage.paste(img2, (img_width + self.spacing, 0))

    def arrange_three_images(self, collage, images, formats, width, height):
        """
        Layouts für drei Bilder.
        """
        layouts = [
            # Ein großes Bild oben, zwei kleinere unten nebeneinander
            lambda imgs: [
                (self.crop_and_resize(imgs[0], width, int(height * 0.6) - self.spacing), (0, 0)),
                (self.crop_and_resize(imgs[1], int(width * 0.5), int(height * 0.4)), (0, int(height * 0.6))),
                (self.crop_and_resize(imgs[2], int(width * 0.5), int(height * 0.4)),
                 (int(width * 0.5) + self.spacing, int(height * 0.6))),
            ],
            # Großes Hochformat links, zwei Querformat rechts übereinander
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(width * 0.4), height), (0, 0)),
                (self.crop_and_resize(imgs[1], int(width * 0.6), int(height * 0.5)), (int(width * 0.4) + self.spacing, 0)),
                (self.crop_and_resize(imgs[2], int(width * 0.6), int(height * 0.5)-self.spacing), (int(width * 0.4) + self.spacing, int(height * 0.5) + self.spacing)),
            ],
            # Drei gleich große Bilder im Hochformat nebeneinander
            lambda imgs: [
                (self.crop_and_resize(img, int(width / 3) - self.spacing, height), (i * (int(width / 3)), 0))
                for i, img in enumerate(imgs)
            ],
        ]

        if formats.count("portrait") == 0:
            layout = layouts[0]
        elif formats.count("portrait") == 1:
            layout = layouts[1]
        elif formats.count("portrait") >= 2:
            layout = layouts[2]

        for img, pos in layout(images):
            collage.paste(img, pos)

    def arrange_four_images(self, collage, images, formats, width, height):
        """
        Layouts für vier Bilder.
        """
        layouts = [
            # Großes Bild links, drei kleine rechts
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(width * 0.6), height), (0, 0)),
                (self.crop_and_resize(imgs[1], int(width * 0.4), int(height / 3)), (int(width * 0.6) + self.spacing, 0)),
                (self.crop_and_resize(imgs[2], int(width * 0.4), int(height / 3)-self.spacing), (int(width * 0.6) + self.spacing, int(height / 3) + self.spacing)),
                (self.crop_and_resize(imgs[3], int(width * 0.4), int(height / 3)-1*self.spacing), (int(width * 0.6) + self.spacing, int(height * 2 / 3) + self.spacing*1)),
            ],
            # Zwei große Bilder oben, zwei kleine unten
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(width * 0.45), int(height * 0.55)-self.spacing), (0, 0)),
                (self.crop_and_resize(imgs[1], int(width * 0.55), int(height * 0.55)-self.spacing), (int(width * 0.45) + self.spacing, 0)),
                (self.crop_and_resize(imgs[2], int(width * 0.55), int(height * 0.45)), (0, int(height * 0.55))),
                (self.crop_and_resize(imgs[3], int(width * 0.45), int(height * 0.45)), (int(width * 0.55) + self.spacing, int(height * 0.55))),
            ],
            # Vier gleich große Bilder
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(width * 0.5), int(height * 0.5-int(self.spacing/2))), (0, 0)),
                (self.crop_and_resize(imgs[1], int(width * 0.5), int(height * 0.5-int(self.spacing/2))), (int(width * 0.5) + self.spacing, 0)),
                (self.crop_and_resize(imgs[2], int(width * 0.5), int(height * 0.5-int(self.spacing/2))), (0, int(height * 0.5)+int(self.spacing/2))),
                (self.crop_and_resize(imgs[3], int(width * 0.5), int(height * 0.5-int(self.spacing/2))), (int(width * 0.5) + self.spacing, int(height * 0.5)+int(self.spacing/2))),
            ],

        ]

        layout = layouts[0] if formats.count("portrait") >= 1 else layouts[2]
        for img, pos in layout(images):
            collage.paste(img, pos)

    def arrange_multiple_images(self, collage, images, width, height):
        """
        Raster-Layout für mehr als vier Bilder, mit Größenvariation.
        """
        cols = 3
        rows = (len(images) + cols - 1) // cols
        cell_width = (width - (cols - 1) * self.spacing) // cols
        cell_height = (height - (rows - 1) * self.spacing) // rows

        for i, img in enumerate(images):
            row = i // cols
            col = i % cols
            w_variation = 1.0 + (0.1 * (-1 if i % 2 == 0 else 1))
            h_variation = 1.0 + (0.1 * (-1 if i % 3 == 0 else 1))
            target_width = int(cell_width * w_variation)
            target_height = int(cell_height * h_variation)
            resized_img = self.crop_and_resize(img, target_width, target_height)
            x_offset = col * (cell_width + self.spacing)
            y_offset = row * (cell_height + self.spacing)
            collage.paste(resized_img, (x_offset, y_offset))

def generateWeekCollages():
    """
    Testfunktion: Generiert Collagen für alle Wochen aus dem Ordner ../res/images.
    """
    base_dir = "../res/images"
    output_dir = "temp/collages"
    os.makedirs(output_dir, exist_ok=True)

    for weekIndex, folder in enumerate(sorted(os.listdir(base_dir))):
        folder_path = os.path.join(base_dir, folder)
        if os.path.isdir(folder_path):
            # Sammle alle Bilddateien im aktuellen Ordner
            image_files = [
                os.path.join(folder_path, file)
                for file in sorted(os.listdir(folder_path))
                if file.lower().endswith((".png", ".jpg", ".jpeg"))
            ]

            if not image_files:
                print(f"Keine Bilder in {folder_path} gefunden, überspringe...")
                continue

            # Generiere den Ausgabe-Pfad basierend auf dem Ordnernamen
            output_file_name = f"collage_{folder}.jpg"
            output_path = os.path.join(output_dir, output_file_name)

            # Collage generieren
            print(f"Generiere Collage für Ordner: {folder}")
            CollageGenerator().generate_collage(image_files, weekIndex, output_path)


def generateDifferentLayouts():
    """
    Testfunktion: Generiert Collagen mit verschiedenen Layouts und Bildkombinationen
    aus dem Ordner ../res/images.
    """
    base_dir = "../res/images"
    output_dir = "temp/collages"
    os.makedirs(output_dir, exist_ok=True)

    # Sammle alle Bilddateien (auf oberster Ebene)
    image_files = [
        os.path.join(base_dir, file)
        for file in sorted(os.listdir(base_dir))
        if file.lower().endswith((".png", ".jpg", ".jpeg"))
    ]

    if not image_files:
        print(f"Keine Bilder in {base_dir} gefunden. Abbruch.")
        return

    # Trenne Bilder in landscape und portrait basierend auf Dateinamen
    landscape_images = [f for f in image_files if "landscape" in os.path.basename(f).lower()]
    portrait_images = [f for f in image_files if "portrait" in os.path.basename(f).lower()]

    if not landscape_images or not portrait_images:
        print("Es werden sowohl 'landscape'- als auch 'portrait'-Bilder benötigt.")
        return

    print("Starte Generierung von Collagen mit verschiedenen Layouts...")

    layout_configurations = [
        (1, ["landscape"]),  # 1 Bild: 1x landscape
        (1, ["portrait"]),   # 1 Bild: 1x portrait
        (2, ["landscape", "landscape"]),  # 2 Bilder: 2x landscape
        (2, ["portrait", "portrait"]),    # 2 Bilder: 2x portrait
        (2, ["landscape", "portrait"]),   # 2 Bilder: 1x landscape, 1x portrait
        (3, ["landscape", "landscape", "landscape"]),  # 3 Bilder: 3x landscape
        (3, ["portrait", "portrait", "portrait"]),     # 3 Bilder: 3x portrait
        (3, ["landscape", "landscape", "portrait"]),   # 3 Bilder: 2x landscape, 1x portrait
        (3, ["landscape", "portrait", "portrait"]),    # 3 Bilder: 1x landscape, 2x portrait
        (4, ["landscape", "landscape", "landscape", "landscape"]),  # 4 Bilder: 4x landscape
        (4, ["landscape", "landscape", "landscape", "portrait"]),   # 4 Bilder: 3x landscape, 1x portrait
        (4, ["landscape", "landscape", "portrait", "portrait"]),    # 4 Bilder: 2x landscape, 2x portrait
        (4, ["landscape", "portrait", "portrait", "portrait"]),     # 4 Bilder: 1x landscape, 3x portrait
        (5, ["landscape", "landscape", "portrait", "portrait", "portrait"]),  # Beispiele für 5 Bilder
        (6, ["landscape", "landscape", "landscape", "portrait", "portrait", "portrait"]),  # Beispiele für 6 Bilder
    ]

    for index, (num_images, layout) in enumerate(layout_configurations):
        # Wähle Bilder basierend auf Layout
        landscape_pointer = 0
        portrait_pointer = 0
        selected_images = []
        for img_type in layout:
            if img_type == "landscape" and landscape_images:
                selected_images.append(landscape_images[landscape_pointer])
                landscape_pointer+=1
            elif img_type == "portrait" and portrait_images:
                selected_images.append(portrait_images[portrait_pointer])
                portrait_pointer+=1

        # Skip, wenn nicht genug Bilder für die Kombination vorhanden sind
        if len(selected_images) < num_images:
            print(f"Nicht genügend Bilder für Layout {layout}. Überspringe...")
            continue

        # Generiere den Ausgabe-Pfad
        output_file_name = f"collage_layout_{index + 1}.jpg"
        output_path = os.path.join(output_dir, output_file_name)

        # Collage generieren
        print(f"Generiere Collage für Layout: {layout}")
        CollageGenerator().generate_collage(selected_images, index, output_path)



if __name__ == "__main__":
    #generateWeekCollages()
    generateDifferentLayouts()

