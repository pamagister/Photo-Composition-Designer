import os

from PIL import Image

from common.config import Config
from snapcalendar.collage.calendarGenerator import CalendarGenerator
from snapcalendar.collage.descriptionGenerator import DescriptionGenerator
from snapcalendar.collage.mapGenerator import MapGenerator


class CollageGenerator:
    def __init__(self, config=None):
        self.config = config or Config()
        self.calendarium_height = self.config.calendarHeight
        self.width = self.config.width
        self.height = self.config.height
        self.spacing = self.config.spacing
        self.calendarObj = CalendarGenerator(self.config)
        self.descGenerator = DescriptionGenerator()
        self.mapGenerator = MapGenerator()

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

    def generate_collage(self, image_files, week, output_path, photo_description=''):
        """
        Erzeugt eine Collage mit Bildern, einem Calendarium und einer Europakarte mit Foto-Locations.
        """
        collage = Image.new("RGB", (self.width, self.height), self.config.backgroundColor)
        calendarImage = self.calendarObj.generateCalendarium(week)
        collage.paste(calendarImage, (0, self.height - self.calendarium_height))

        if self.config.usePhotoDescription:
            descriptionImage = self.descGenerator.generateDescription(photo_description)
            collage.paste(descriptionImage, (0, self.height - self.calendarium_height - self.descGenerator.height))

        available_height = self.height - self.calendarium_height - self.descGenerator.height
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
        elif len(images) == 5:
            self.arrange_five_images(collage, images, formats, available_width, available_height)
        else:
            self.arrange_multiple_images(collage, images, available_width, available_height)

        # Wenn GPS-Koordinaten vorliegen, eine Karte generieren
        if self.config.usePhotoLocationMaps:
            # EXIF-Daten auslesen und GPS-Koordinaten extrahieren
            gps_coords = []
            for img_path in image_files:
                coords = self.mapGenerator.extract_gps_coordinates(img_path)
                if coords:
                    gps_coords.append(coords)
            map_image = self.mapGenerator.generate_map(gps_coords)
            map_image_resized = map_image.resize((self.calendarium_height, self.calendarium_height))
            collage.paste(map_image_resized, (self.width-self.calendarium_height, self.height - self.calendarium_height))

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

    def arrange_three_images(self, collage, images, formats, w, h):
        """
        Layouts für drei Bilder.
        """
        s = self.spacing
        layouts = [
            # Ein großes Bild oben, zwei kleinere unten nebeneinander
            lambda imgs: [
                (self.crop_and_resize(imgs[0], w, int(h * 0.6) - s), (0, 0)),
                (self.crop_and_resize(imgs[1], int(w * 0.5), int(h * 0.4)), (0, int(h * 0.6))),
                (self.crop_and_resize(imgs[2], int(w * 0.5), int(h * 0.4)),
                 (int(w * 0.5) + s, int(h * 0.6))),
            ],
            # Großes Hochformat links, zwei Querformat rechts übereinander
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(w * 0.4), h), (0, 0)),
                (self.crop_and_resize(imgs[1], int(w * 0.6), int(h * 0.5)), (int(w * 0.4) + s, 0)),
                (self.crop_and_resize(imgs[2], int(w * 0.6), int(h * 0.5) - s), (int(w * 0.4) + s, int(h * 0.5) + s)),
            ],
            # Drei gleich große Bilder im Hochformat nebeneinander
            lambda imgs: [
                (self.crop_and_resize(img, int(w / 3) - s, h), (i * (int(w / 3)), 0))
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

    def arrange_four_images(self, collage, images, formats, w, h):
        """
        Layouts für vier Bilder.
        """
        s = self.spacing
        layouts = [
            # Zwei große Bilder oben, zwei kleine unten (LLLL)
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(w * 0.45), int(h * 0.55) - s), (0, 0)),
                (self.crop_and_resize(imgs[3], int(w * 0.55), int(h * 0.55) - s), (int(w * 0.45) + s, 0)),
                (self.crop_and_resize(imgs[2], int(w * 0.55), int(h * 0.45)), (0, int(h * 0.55))),
                (self.crop_and_resize(imgs[1], int(w * 0.45), int(h * 0.45)), (int(w * 0.55) + s, int(h * 0.55))),
            ],
            # Großes portrait-Bild links, drei kleine landscape rechts
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(w * 0.6), h), (0, 0)),  # portrait, index 0
                (self.crop_and_resize(imgs[1], int(w * 0.4), int(h / 3)), (int(w * 0.6) + s, 0)),
                (self.crop_and_resize(imgs[2], int(w * 0.4), int(h / 3) - s), (int(w * 0.6) + s, int(h / 3) + s)),
                (self.crop_and_resize(imgs[3], int(w * 0.4), int(h / 3) - 1 * s), (int(w * 0.6) + s, int(h * 2 / 3) + s * 1)),
            ],
            # Großes portrait-Bild links, rechts oben landscape, darunter zwei kleine landscape nebeneinander
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(w * 0.4), h), (0, 0)),  # portrait, index 0
                (self.crop_and_resize(imgs[1], int(w * 0.6), int(h * 3 / 5)), (int(w * 0.4) + s, 0)),
                (self.crop_and_resize(imgs[2], int(w * 0.3 - s), int(h * 2 / 5) - s), (int(w * 0.4) + s, int(h * 3 / 5) + s)),  # portrait, index 1
                (self.crop_and_resize(imgs[3], int(w * 0.3 - s), int(h * 2 / 5) - s), (int(w * 0.7) + s, int(h * 3 / 5) + s)),
            ],

            # Großes portrait-Bild links, rechts oben landscape, darunter kleines portrait und landscape nebeneinander
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(w * 0.4), h), (0, 0)),  # portrait, index 0
                (self.crop_and_resize(imgs[2], int(w * 0.6), int(h*3/5)), (int(w * 0.4) + s, 0)),
                (self.crop_and_resize(imgs[1], int(w * 0.2), int(h*2/5) - s), (int(w * 0.4) + s, int(h*3/5) + s)),  # portrait, index 1
                (self.crop_and_resize(imgs[3], int(w * 0.4-2*s), int(h*2/5) - s), (int(w * 0.6) + 2*s, int(h*3/5) + s)),
            ],
            # Großes portrait-Bild links, rechts oben landscape, darunter zwei kleines portrait nebeneinander
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(w * 0.4), h), (0, 0)),  # portrait, index 0
                (self.crop_and_resize(imgs[3], int(w * 0.6), int(h * 2 / 5)), (int(w * 0.4) + s, 0)),
                (self.crop_and_resize(imgs[1], int(w * 0.25), int(h * 3 / 5) - s), (int(w * 0.4) + s, int(h * 2 / 5) + s)),  # portrait, index 1
                (self.crop_and_resize(imgs[2], int(w * 0.35 - 2 * s), int(h * 3 / 5) - s), (int(w * 0.65) + 2 * s, int(h * 2 / 5) + s)),  # portrait, index 2
            ],

        ]

        if formats.count("portrait") == 0:  # LLLL = 4x landscape
            layout = layouts[0]
        elif formats.count("portrait") == 1:  # PLLL
            layout = layouts[2]
        elif formats.count("portrait") == 2:  # PPLL
            layout = layouts[3]
        elif formats.count("portrait") >= 3:  # PPPL
            layout = layouts[4]

        for img, pos in layout(images):
            collage.paste(img, pos)

    def arrange_five_images(self, collage, images, formats, w, h):
        """
        Layouts für fünf Bilder.
        """
        s = self.spacing
        layouts = [
            # Zwei große Bilder oben, drei etwas kleinere unten (LLLLL)
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(w * 0.5), int(h * 0.6) - s), (0, 0)),  # portrait, index 0
                (self.crop_and_resize(imgs[1], int(w * 0.5), int(h * 0.6) - s), (int(w * 0.5) + s, 0)),
                (self.crop_and_resize(imgs[2], int(w / 3), int(h * 0.4)), (int(w * 0 / 3) + 0 * s, int(h * 0.6))),
                (self.crop_and_resize(imgs[3], int(w / 3), int(h * 0.4)), (int(w * 1 / 3) + 1 * s, int(h * 0.6))),
                (self.crop_and_resize(imgs[4], int(w / 3), int(h * 0.4)), (int(w * 2 / 3) + 2 * s, int(h * 0.6))),
            ],# großes Portrait links oben, großes landscape rechts oben, unten drei kleine landscape (PLLLL)
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(w * 0.3), int(h * 2 / 3) - s), (0, 0)),  # portrait, index 0
                (self.crop_and_resize(imgs[1], int(w * 0.7), int(h * 2 / 3) - s), (int(w * 0.3) + s, 0)),
                (self.crop_and_resize(imgs[4], int(w / 3), int(h / 3)), (int(w * 0 / 3) + 0*s, int(h * 2/3))),
                (self.crop_and_resize(imgs[3], int(w / 3), int(h / 3)), (int(w * 1 / 3) + 1*s, int(h * 2/3))),
                (self.crop_and_resize(imgs[2], int(w / 3), int(h / 3)), (int(w * 2 / 3) + 2*s, int(h * 2/3))),
            ],
            # zwei großes Portrais oben,  unten drei kleine landscape  (PPLLL)
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(w * 0.5), int(h * 2 / 3) - s), (0, 0)),  # portrait, index 0
                (self.crop_and_resize(imgs[1], int(w * 0.5), int(h * 2 / 3) - s), (int(w * 0.5) + s, 0)),
                (self.crop_and_resize(imgs[4], int(w / 3), int(h / 3)), (int(w * 0 / 3) + 0 * s, int(h * 2 / 3))),
                (self.crop_and_resize(imgs[3], int(w / 3), int(h / 3)), (int(w * 1 / 3) + 1 * s, int(h * 2 / 3))),
                (self.crop_and_resize(imgs[2], int(w / 3), int(h / 3)), (int(w * 2 / 3) + 2 * s, int(h * 2 / 3))),
            ],
            # Links ein großes Portrait, rechts daneben im goldenen Schnitt vier kleinere Bilder kleine unten (PPPLL)
            lambda imgs: [
                (self.crop_and_resize(imgs[0], int(w * 0.35-s), int(h)), (0, 0)),  # portrait, index 0
                (self.crop_and_resize(imgs[1], int(w * 0.25), int(h * 0.55) - s), (int(w * 0.35), 0)),
                (self.crop_and_resize(imgs[2], int(w * 0.40) - s, int(h * 0.55) - s), (int(w * 0.6) + s, 0)),
                (self.crop_and_resize(imgs[3], int(w * 0.40), int(h * 0.45)), (int(w * 0.35), int(h * 0.55))),
                (self.crop_and_resize(imgs[4], int(w * 0.25) - s, int(h * 0.45)), (int(w * 0.75) + s, int(h * 0.55))),
            ],

        ]

        if formats.count("portrait") == 0:  # LLLLL = 5x landscape
            layout = layouts[0]
        elif formats.count("portrait") == 1:  # PLLLL
            layout = layouts[1]
        elif formats.count("portrait") == 2:  # PPLLL
            layout = layouts[2]
        elif formats.count("portrait") >= 3:  # PPPLL
            layout = layouts[3]

        for img, pos in layout(images):
            collage.paste(img, pos)

    def arrange_multiple_images(self, collage, images, width, height):
        """
        Raster-Layout für mehr als vier Bilder, mit gleichmäßiger Verteilung.
        Passt automatisch die Anzahl der Zeilen und Spalten an.
        """
        # Bestimme die Anzahl der Spalten und Zeilen basierend auf der Anzahl der Bilder
        rows = int(len(images) ** 0.5)  # Quadratwurzel für möglichst gleichmäßige Aufteilung
        cols = (len(images) + rows - 1) // rows  # Rundung nach oben

        # Berechnung der Zellgrößen basierend auf der Collage-Größe und Abstände
        cell_width = (width - (cols - 1) * self.spacing) // cols
        cell_height = (height - (rows - 1) * self.spacing) // rows

        # Bilder in das Raster einfügen
        for i, img in enumerate(images):
            # Bestimme Zeile und Spalte des aktuellen Bildes
            row = i // cols
            col = i % cols

            # Passe die Bildgröße an die Rasterzelle an
            resized_img = self.crop_and_resize(img, cell_width, cell_height)

            # Berechne die Position des Bildes in der Collage
            x_offset = col * (cell_width + self.spacing)
            y_offset = row * (cell_height + self.spacing)

            # Füge das Bild in die Collage ein
            collage.paste(resized_img, (x_offset, y_offset))

    def arrange_multiple_images2(self, collage, images, width, height):
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

def generateWeekCollages(output_dir):
    """
    Testfunktion: Generiert Collagen für alle Wochen aus dem Ordner ../res/images.
    """
    base_dir = "../res/images"
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
            CollageGenerator().generate_collage(image_files, weekIndex+30, output_path)


def generateDifferentLayouts(output_dir):
    """
    Testfunktion: Generiert Collagen mit verschiedenen Layouts und Bildkombinationen
    aus dem Ordner ../res/images.
    """
    base_dir = "../res/images"
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
        (5, ["landscape", "landscape", "landscape", "landscape", "landscape"]),  # 5 Bilder: 5x landscape
        (5, ["landscape", "landscape", "landscape", "landscape", "portrait"]),  # Beispiele für 5 Bilder
        (5, ["landscape", "landscape", "landscape", "portrait", "portrait"]),  # Beispiele für 5 Bilder
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
    output_dir = "../temp/collages"
    generateWeekCollages(output_dir)
    #generateDifferentLayouts(output_dir)

