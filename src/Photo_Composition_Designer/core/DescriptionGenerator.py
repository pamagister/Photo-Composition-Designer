from PIL import Image, ImageDraw, ImageFont


class DescriptionGenerator:
    def __init__(
        self, width: int, fontSizeSmall, spacing, marginSides, backgroundColor, textColor2
    ):
        self.width = int(width)  # Die Breite des erzeugten Bildes.
        self.fontSize = fontSizeSmall  # Die Schriftgröße des Textes.
        self.spacing = spacing
        self.height = int(self.fontSize + self.spacing)  # Die Höhe des erzeugten Bildes.
        self.margin_side = marginSides
        self.textColor2 = textColor2
        self.backgroundColor = backgroundColor

    def generateDescription(self, text):
        """
        Erzeugt ein Bild mit dem angegebenen Text.
        :param text: Der darzustellende Text.
        :return: Ein PIL Image-Objekt mit dem gerenderten Text.
        """
        # Erstelle ein neues Bild mit der Hintergrundfarbe aus der Konfiguration
        description_image = Image.new("RGB", (self.width, self.height), self.backgroundColor)

        # Zeichnungsobjekt initialisieren
        draw = ImageDraw.Draw(description_image)

        # Schrift laden (Standard oder konfiguriert)
        try:
            font = ImageFont.truetype("DejaVuSansCondensed.ttf", int(self.fontSize))
        except Exception as e:
            print(f"Fehler beim Laden der Schriftart: {e}")
            font = ImageFont.load_default()

        # Text zeichnen
        draw.text(
            (self.margin_side, self.height),
            text,
            fill=self.textColor2,
            font=font,
            anchor="lb",
        )

        return description_image
