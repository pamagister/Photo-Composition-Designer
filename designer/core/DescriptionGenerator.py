from PIL import Image, ImageDraw, ImageFont

from designer.common.Config import Config


class DescriptionGenerator:
    def __init__(self, config=None):
        self.config = config or Config()
        self.width = int(self.config.width)  # Die Breite des erzeugten Bildes.
        self.fontSize = self.config.fontSizeSmall  # Die Schriftgröße des Textes.
        self.spacing = self.config.spacing
        self.height = int(self.fontSize + self.spacing)  # Die Höhe des erzeugten Bildes.
        self.margin_side = self.config.marginSides

    def generateDescription(self, text):
        """
        Erzeugt ein Bild mit dem angegebenen Text.
        :param text: Der darzustellende Text.
        :return: Ein PIL.Image-Objekt mit dem gerenderten Text.
        """
        # Erstelle ein neues Bild mit der Hintergrundfarbe aus der Konfiguration
        description_image = Image.new("RGB", (self.width, self.height), self.config.backgroundColor)

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
            fill=self.config.textColor2,
            font=font,
            anchor="lb",
        )

        return description_image
