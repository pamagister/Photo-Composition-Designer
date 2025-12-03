from io import BytesIO
from pathlib import Path

import exifread
from PIL import Image

from Photo_Composition_Designer.common.Locations import Locations
from Photo_Composition_Designer.tools.GeoPlotter import GeoPlotter


class MapRenderer:
    def __init__(
        self,
        mapHeight=100,
        mapWidth=100,
        minimalExtension=7,
        backgroundColor=(30, 30, 30),
        textColor1=(150, 250, 150),
        locations: Locations = None,
    ):
        self.height = mapHeight
        self.width = mapWidth
        self.minimalExtension = minimalExtension
        self.backgroundColor = backgroundColor
        self.textColor1 = textColor1
        self.locations = locations or Locations()

    def generate(self, coordinates: list[tuple[float, float]]) -> Image.Image:
        """
        Generiert eine Karte als Bild mit den GPS-Koordinaten.
        :param coordinates: Liste von (Breitengrad, Längengrad)-Tupeln.
        :return: PIL.Image-Objekt mit der Karte.
        """
        # Plotter initialisieren
        border = 15  # unwanted border to be eliminated
        plotter = GeoPlotter(
            minimalExtension=self.minimalExtension,
            size=(self.width + 2 * border, self.height + 2 * border),
            background_color=self.backgroundColor,
            border_color=self.textColor1,
        )

        # GeoDataFrame aus Koordinaten erstellen
        plt = plotter.renderMap(coordinates)

        # In einen BytesIO-Puffer speichern
        buf = BytesIO()
        plt.savefig(buf, format="PNG", bbox_inches="tight")  # Optional: Anpassung des DPI-Werts
        plt.close()  # Speicher freigeben
        buf.seek(0)

        map_image: Image.Image = Image.open(buf)
        map_image = map_image.resize((self.width + 2 * border, self.height + 2 * border))
        map_image = map_image.crop((border, border, self.width + border, self.height + border))

        # Puffer als PIL.Image öffnen und zurückgeben
        return map_image

    def extract_gps_coordinates(self, img_path):
        """
        Liest die GPS-Koordinaten aus den EXIF-Daten eines Bildes.
        """
        with open(img_path, "rb") as img_file:
            tags = exifread.process_file(img_file, details=False)
            if "GPS GPSLatitude" in tags and "GPS GPSLongitude" in tags:
                lat = self.convert_to_decimal(tags["GPS GPSLatitude"].values)
                lon = self.convert_to_decimal(tags["GPS GPSLongitude"].values)
                if tags.get("GPS GPSLatitudeRef") == "S":
                    lat = -lat
                if tags.get("GPS GPSLongitudeRef") == "W":
                    lon = -lon
                return lat, lon
        return None

    @staticmethod
    def convert_to_decimal(dms: list[int]) -> float:
        """
        Konvertiert Grad, Minuten und Sekunden in Dezimalgrad.
        """
        return dms[0] + dms[1] / 60 + dms[2] / 3600


if __name__ == "__main__":
    for size in range(100, 900, 200):
        map_plt = Image.new(mode="RGB", size=(size, size))

        project_root = Path(__file__).resolve().parents[3]
        temp_dir = project_root / "temp"
        temp_dir.mkdir(exist_ok=True)

        gps_coordinates = [
            (51.0504, 13.7373),  # Dresden
            (51.3397, 12.3731),  # Leipzig
            (50.8278, 12.9214),  # Chemnitz
            (51.1079, 17.0441),  # Breslau
            (52.5200, 13.5156),  # Berlin
        ]
        map_generator = MapRenderer()
        map_generator.height = size
        map_generator.width = size

        img = map_generator.generate(gps_coordinates)

        map_plt.paste(img)
        map_plt.save(temp_dir / f"map_{size}.jpg")
