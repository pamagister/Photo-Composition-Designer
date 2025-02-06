import os.path
from io import BytesIO
from pathlib import Path

import exifread
from PIL import Image

from designer.common.Config import Config
from designer.common.Locations import Locations
from designer.geo.GeoPlotter import GeoPlotter


class MapGenerator:
    def __init__(self, config=None):
        self.config = config or Config()
        self.height = self.config.mapHeight
        self.width = self.config.mapWidth
        self.locations = Locations(self.config.locationsConfig)

    def generateImageLocationMap(self, image_files):
        # Read EXIF data and extract GPS coordinates
        coordinatesList = []
        for img_path in image_files:
            coordinates = self.extract_gps_coordinates(img_path)
            file_name = str(os.path.splitext(os.path.basename(img_path))[0]).lower()
            if coordinates:
                coordinatesList.append(coordinates)
            elif file_name in self.locations.locations_dict.keys():
                coordinatesList.append(self.locations.locations_dict[file_name])
        map_image = self.generate_map(coordinatesList)

        return map_image

    def generate_map(self, gps_coords):
        """
        Generiert eine Karte als Bild mit den GPS-Koordinaten.
        :param gps_coords: Liste von (Breitengrad, Längengrad)-Tupeln.
        :return: PIL.Image-Objekt mit der Karte.
        """
        # Plotter initialisieren
        border = 15  # unwanted border to be eliminated
        plotter = GeoPlotter(
            minimalExtension=self.config.minimalExtension,
            size=(self.width + 2 * border, self.height + 2 * border),
            background_color=self.config.backgroundColor,
            border_color=self.config.textColor1,
        )

        # GeoDataFrame aus Koordinaten erstellen
        plt = plotter.renderMap(gps_coords)

        # In einen BytesIO-Puffer speichern
        buf = BytesIO()
        plt.savefig(buf, format="PNG", bbox_inches="tight")  # Optional: Anpassung des DPI-Werts
        plt.close()  # Speicher freigeben
        buf.seek(0)

        map_image = Image.open(buf)
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

    def convert_to_decimal(self, dms):
        """
        Konvertiert Grad, Minuten und Sekunden in Dezimalgrad.
        """
        return dms[0] + dms[1] / 60 + dms[2] / 3600


if __name__ == "__main__":
    for size in range(100, 900, 200):
        map_plt = Image.new(mode="RGB", size=(size, size))
        output_dir = Path.cwd()
        gps_coordinates = [
            (51.0504, 13.7373),  # Dresden
            (51.3397, 12.3731),  # Leipzig
            (50.8278, 12.9214),  # Chemnitz
            (51.1079, 17.0441),  # Breslau
            (52.5200, 13.5156),  # Berlin
        ]
        map_generator = MapGenerator()
        map_generator.height = size
        map_generator.width = size

        img = map_generator.generate_map(gps_coordinates)

        map_plt.paste(img)
        map_plt.save(output_dir / f"map_{size}.jpg")
