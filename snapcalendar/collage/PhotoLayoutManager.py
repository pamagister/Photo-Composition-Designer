from PIL import Image, UnidentifiedImageError


class PhotoLayoutManager:
    def __init__(self, collage, width=900, height=600, spacing=10):
        self.collage = collage
        self.width = width
        self.height = height
        self.spacing = spacing


    @staticmethod
    def filterInvalidImages(image_files):
        """
        Überprüft eine Liste von Bildern und entfernt nicht lesbare oder kaputte Bilder.
        """
        valid_images = []
        for img_file in image_files:
            try:
                # Teste, ob das Bild ohne Fehler zugeschnitten werden kann
                img = Image.open(img_file)
                img.crop((0, 2, 3, 3))
                valid_images.append(img_file)
            except (UnidentifiedImageError, OSError) as e:
                print(f"Invalid image skipped: {img_file} - {e}")

        # Öffne die Bilder erneut, da der Dateizeiger möglicherweise geschlossen wurde
        return valid_images

    def arrangeImages(self, image_files):
        """
        Ordnet die Bilder in der Collage an. Bilder werden vorab auf Lesbarkeit geprüft.
        """
        # Bilder nach Seitenverhältnis sortieren
        images = [Image.open(img) for img in image_files]
        images = self.sortByAspectRatio(images)
        formats = self.analyzeImages(images)

        try:
            # Anordnungslogik basierend auf Bildanzahl
            if len(images) == 1:
                self.arrangeOneImage(self.collage, images[0], self.width, self.height)
            elif len(images) == 2:
                self.arrangeTwoImages(self.collage, images, formats, self.width, self.height)
            elif len(images) == 3:
                self.arrangeThreeImages(self.collage, images, formats, self.width, self.height)
            elif len(images) == 4:
                self.arrangeFourImages(self.collage, images, formats, self.width, self.height)
            elif len(images) == 5:
                self.arrangeFiveImages(self.collage, images, formats, self.width, self.height)
            else:
                self.arrangeMultipleImages(self.collage, images, self.width, self.height)
        except (UnidentifiedImageError, OSError) as e:
            print(f"Error in the arrangement of images: {e}")
            # Entferne ungültige Bilder und versuche es erneut
            image_files = self.filterInvalidImages(image_files)
            if image_files:
                print("Invalid images removed, try again...")
                self.arrangeImages(image_files)
            else:
                # Wenn keine gültigen Bilder mehr vorhanden sind, Fehler erneut werfen
                print("No more valid images available.")
                raise e

    @staticmethod
    def analyzeImages(images):
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

    @staticmethod
    def sortByAspectRatio(images):
        """
        Sortiert Bilder basierend auf ihrem Seitenverhältnis (Breite / Höhe).
        Schmalste ("portrait") zuerst, breiteste ("landscape") zuletzt.
        """
        return sorted(images, key=lambda img: img.size[0] / img.size[1], reverse=False)

    @staticmethod
    def cropAndResize(image, target_width, target_height):
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

    def arrangeOneImage(self, collage, image, width, height):
        """
        Layout für ein einzelnes Bild.
        """
        img = self.cropAndResize(image, width, height)
        collage.paste(img, (0, 0))

    def arrangeTwoImages(self, collage, images, formats, width, height):
        """
        Layout für zwei Bilder.
        """
        if "portrait" in formats:
            portrait_idx = formats.index("portrait")
            landscape_idx = 1 - portrait_idx
            # Goldener Schnitt Layout
            portrait_width = int(width * 0.4)
            landscape_width = width - portrait_width - self.spacing
            img1 = self.cropAndResize(images[portrait_idx], portrait_width, height)
            img2 = self.cropAndResize(images[landscape_idx], landscape_width, height)
            collage.paste(img1, (0, 0))
            collage.paste(img2, (portrait_width + self.spacing, 0))
        else:
            # Beide Querformat -> nebeneinander
            img_width = (width - self.spacing) // 2
            img1 = self.cropAndResize(images[0], img_width, height)
            img2 = self.cropAndResize(images[1], img_width, height)
            collage.paste(img1, (0, 0))
            collage.paste(img2, (img_width + self.spacing, 0))

    def arrangeThreeImages(self, collage, images, formats, w, h):
        """
        Layouts für drei Bilder.
        """
        s = self.spacing
        layouts = [
            # Ein großes Bild oben, zwei kleinere unten nebeneinander
            lambda imgs: [
                (self.cropAndResize(imgs[0], w, int(h * 0.6) - s), (0, 0)),
                (self.cropAndResize(imgs[1], int(w * 0.5), int(h * 0.4)), (0, int(h * 0.6))),
                (self.cropAndResize(imgs[2], int(w * 0.5), int(h * 0.4)), (int(w * 0.5) + s, int(h * 0.6))),
            ],
            # Großes Hochformat links, zwei Querformat rechts übereinander
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.4), h), (0, 0)),
                (self.cropAndResize(imgs[1], int(w * 0.6), int(h * 0.5)), (int(w * 0.4) + s, 0)),
                (self.cropAndResize(imgs[2], int(w * 0.6), int(h * 0.5) - s), (int(w * 0.4) + s, int(h * 0.5) + s)),
            ],
            # Drei gleich große Bilder im Hochformat nebeneinander
            lambda imgs: [
                (self.cropAndResize(img, int(w / 3) - s, h), (i * (int(w / 3)), 0)) for i, img in enumerate(imgs)
            ],
        ]

        if formats.count("portrait") == 0:
            layout = layouts[0]
        elif formats.count("portrait") == 1:
            layout = layouts[1]
        else:
            layout = layouts[2]

        for img, pos in layout(images):
            collage.paste(img, pos)

    def arrangeFourImages(self, collage, images, formats, w, h):
        """
        Layouts für vier Bilder.
        """
        s = self.spacing
        layouts = [
            # Zwei große Bilder oben, zwei kleine unten (LLLL)
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.45), int(h * 0.55) - s), (0, 0)),
                (self.cropAndResize(imgs[3], int(w * 0.55), int(h * 0.55) - s), (int(w * 0.45) + s, 0)),
                (self.cropAndResize(imgs[2], int(w * 0.55), int(h * 0.45)), (0, int(h * 0.55))),
                (self.cropAndResize(imgs[1], int(w * 0.45), int(h * 0.45)), (int(w * 0.55) + s, int(h * 0.55))),
            ],
            # Großes portrait-Bild links, drei kleine landscape rechts
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.6), h), (0, 0)),  # portrait, index 0
                (self.cropAndResize(imgs[1], int(w * 0.4), int(h / 3)), (int(w * 0.6) + s, 0)),
                (self.cropAndResize(imgs[2], int(w * 0.4), int(h / 3) - s), (int(w * 0.6) + s, int(h / 3) + s)),
                (
                    self.cropAndResize(imgs[3], int(w * 0.4), int(h / 3) - 1 * s),
                    (int(w * 0.6) + s, int(h * 2 / 3) + s * 1),
                ),
            ],
            # Großes portrait-Bild links, rechts oben landscape, darunter zwei kleine landscape nebeneinander
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.4), h), (0, 0)),  # portrait, index 0
                (self.cropAndResize(imgs[1], int(w * 0.6), int(h * 3 / 5)), (int(w * 0.4) + s, 0)),
                (
                    self.cropAndResize(imgs[2], int(w * 0.3 - s), int(h * 2 / 5) - s),
                    (int(w * 0.4) + s, int(h * 3 / 5) + s),
                ),  # portrait, index 1
                (
                    self.cropAndResize(imgs[3], int(w * 0.3 - s), int(h * 2 / 5) - s),
                    (int(w * 0.7) + s, int(h * 3 / 5) + s),
                ),
            ],
            # Großes portrait-Bild links, rechts oben landscape, darunter kleines portrait und landscape nebeneinander
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.4), h), (0, 0)),  # portrait, index 0
                (self.cropAndResize(imgs[2], int(w * 0.6), int(h * 3 / 5)), (int(w * 0.4) + s, 0)),
                (
                    self.cropAndResize(imgs[1], int(w * 0.2), int(h * 2 / 5) - s),
                    (int(w * 0.4) + s, int(h * 3 / 5) + s),
                ),  # portrait, index 1
                (
                    self.cropAndResize(imgs[3], int(w * 0.4 - 2 * s), int(h * 2 / 5) - s),
                    (int(w * 0.6) + 2 * s, int(h * 3 / 5) + s),
                ),
            ],
            # Großes portrait-Bild links, rechts oben landscape, darunter zwei kleines portrait nebeneinander
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.4), h), (0, 0)),  # portrait, index 0
                (self.cropAndResize(imgs[3], int(w * 0.6), int(h * 2 / 5)), (int(w * 0.4) + s, 0)),
                (
                    self.cropAndResize(imgs[1], int(w * 0.25), int(h * 3 / 5) - s),
                    (int(w * 0.4) + s, int(h * 2 / 5) + s),
                ),  # portrait, index 1
                (
                    self.cropAndResize(imgs[2], int(w * 0.35 - 2 * s), int(h * 3 / 5) - s),
                    (int(w * 0.65) + 2 * s, int(h * 2 / 5) + s),
                ),  # portrait, index 2
            ],
        ]

        if formats.count("portrait") == 0:  # LLLL = 4x landscape
            layout = layouts[0]
        elif formats.count("portrait") == 1:  # PLLL
            layout = layouts[2]
        elif formats.count("portrait") == 2:  # PPLL
            layout = layouts[3]
        else:  # PPPL
            layout = layouts[4]

        for img, pos in layout(images):
            collage.paste(img, pos)

    def arrangeFiveImages(self, collage, images, formats, w, h):
        """
        Layouts für fünf Bilder.
        """
        s = self.spacing
        layouts = [
            # Zwei große Bilder oben, drei etwas kleinere unten (LLLLL)
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.5), int(h * 0.6) - s), (0, 0)),  # portrait, index 0
                (self.cropAndResize(imgs[1], int(w * 0.5), int(h * 0.6) - s), (int(w * 0.5) + s, 0)),
                (self.cropAndResize(imgs[2], int(w / 3), int(h * 0.4)), (int(w * 0 / 3) + 0 * s, int(h * 0.6))),
                (self.cropAndResize(imgs[3], int(w / 3), int(h * 0.4)), (int(w * 1 / 3) + 1 * s, int(h * 0.6))),
                (self.cropAndResize(imgs[4], int(w / 3), int(h * 0.4)), (int(w * 2 / 3) + 2 * s, int(h * 0.6))),
            ],  # großes Portrait links oben, großes landscape rechts oben, unten drei kleine landscape (PLLLL)
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.3), int(h * 2 / 3) - s), (0, 0)),  # portrait, index 0
                (self.cropAndResize(imgs[1], int(w * 0.7), int(h * 2 / 3) - s), (int(w * 0.3) + s, 0)),
                (self.cropAndResize(imgs[4], int(w / 3), int(h / 3)), (int(w * 0 / 3) + 0 * s, int(h * 2 / 3))),
                (self.cropAndResize(imgs[3], int(w / 3), int(h / 3)), (int(w * 1 / 3) + 1 * s, int(h * 2 / 3))),
                (self.cropAndResize(imgs[2], int(w / 3), int(h / 3)), (int(w * 2 / 3) + 2 * s, int(h * 2 / 3))),
            ],
            # zwei großes Portrais oben,  unten drei kleine landscape  (PPLLL)
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.5), int(h * 2 / 3) - s), (0, 0)),  # portrait, index 0
                (self.cropAndResize(imgs[1], int(w * 0.5), int(h * 2 / 3) - s), (int(w * 0.5) + s, 0)),
                (self.cropAndResize(imgs[4], int(w / 3), int(h / 3)), (int(w * 0 / 3) + 0 * s, int(h * 2 / 3))),
                (self.cropAndResize(imgs[3], int(w / 3), int(h / 3)), (int(w * 1 / 3) + 1 * s, int(h * 2 / 3))),
                (self.cropAndResize(imgs[2], int(w / 3), int(h / 3)), (int(w * 2 / 3) + 2 * s, int(h * 2 / 3))),
            ],
            # Links ein großes Portrait, rechts daneben im goldenen Schnitt vier kleinere Bilder kleine unten (PPPLL)
            lambda imgs: [
                (self.cropAndResize(imgs[0], int(w * 0.35 - s), int(h)), (0, 0)),  # portrait, index 0
                (self.cropAndResize(imgs[1], int(w * 0.25), int(h * 0.55) - s), (int(w * 0.35), 0)),
                (self.cropAndResize(imgs[2], int(w * 0.40) - s, int(h * 0.55) - s), (int(w * 0.6) + s, 0)),
                (self.cropAndResize(imgs[3], int(w * 0.40), int(h * 0.45)), (int(w * 0.35), int(h * 0.55))),
                (self.cropAndResize(imgs[4], int(w * 0.25) - s, int(h * 0.45)), (int(w * 0.75) + s, int(h * 0.55))),
            ],
        ]

        if formats.count("portrait") == 0:  # LLLLL = 5x landscape
            layout = layouts[0]
        elif formats.count("portrait") == 1:  # PLLLL
            layout = layouts[1]
        elif formats.count("portrait") == 2:  # PPLLL
            layout = layouts[2]
        else:  # PPPLL
            layout = layouts[3]

        for img, pos in layout(images):
            collage.paste(img, pos)

    def arrangeMultipleImages(self, collage, images, width, height):
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
            resized_img = self.cropAndResize(img, cell_width, cell_height)

            # Berechne die Position des Bildes in der Collage
            x_offset = col * (cell_width + self.spacing)
            y_offset = row * (cell_height + self.spacing)

            # Füge das Bild in die Collage ein
            collage.paste(resized_img, (x_offset, y_offset))
