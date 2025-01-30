from PIL import Image, ImageDraw, ImageFont

from snapcalendar.common.Config import Config


class DescriptionGenerator:
    def __init__(self, config=None):
        self.config = config or Config()
        self.width = int(self.config.width)  # Die Breite des erzeugten Bildes.
        self.fontSize = self.config.fontSizeAnniversaries  # Die Schriftgröße des Textes.
        self.height = int(self.fontSize + self.config.spacing * 2)  # Die Höhe des erzeugten Bildes.
        self.spacing = self.config.spacing

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

        # Textposition zentrieren

        # Text zeichnen
        draw.text((self.spacing, self.spacing), text, fill=self.config.textColor2, font=font, anchor="la")

        return description_image
