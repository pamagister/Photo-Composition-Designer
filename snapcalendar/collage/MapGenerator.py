import exifread
from PIL import Image

from snapcalendar.common.Config import Config
from snapcalendar.geo.GeoPlotter import GeoMapPlotter


class MapGenerator:

    def __init__(self):
        self.config = Config()
        self.height = self.config.mapHeight
        self.width = self.config.mapWidth


    def generateImageLocationMap(self, image_files):
        # Read EXIF data and extract GPS coordinates
        coordinatesList = []
        for img_path in image_files:
            coordinates = self.extract_gps_coordinates(img_path)
            if coordinates:
                coordinatesList.append(coordinates)
        map_image = self.generate_map(coordinatesList)
        map_image_resized = map_image.resize((self.width, self.height))
        return map_image_resized

    def generate_map(self, gps_coords):
        """
        Generiert eine Karte als Bild mit den GPS-Koordinaten.
        :param gps_coords: Liste von (Breitengrad, Längengrad)-Tupeln.
        :return: PIL.Image-Objekt mit der Karte.
        """
        from io import BytesIO

        # Plotter initialisieren
        plotter = GeoMapPlotter(
            buffer_deg=self.config.photoLocationRange,
            resolution=(self.width, self.height),
            background_color=self.config.backgroundColor,
            border_color=self.config.textColor1,
        )

        # GeoDataFrame aus Koordinaten erstellen
        plt = plotter.render_map(gps_coords)

        # In einen BytesIO-Puffer speichern
        buf = BytesIO()
        plt.savefig(buf, format='PNG', bbox_inches='tight', dpi=300)  # Optional: Anpassung des DPI-Werts
        plt.close()  # Speicher freigeben
        buf.seek(0)

        # Puffer als PIL.Image öffnen und zurückgeben
        return Image.open(buf)

    def extract_gps_coordinates(self, img_path):
        """
        Liest die GPS-Koordinaten aus den EXIF-Daten eines Bildes.
        """
        with open(img_path, 'rb') as img_file:
            tags = exifread.process_file(img_file, details=False)
            if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                lat = self.convert_to_decimal(tags['GPS GPSLatitude'].values)
                lon = self.convert_to_decimal(tags['GPS GPSLongitude'].values)
                if tags.get('GPS GPSLatitudeRef') == 'S':
                    lat = -lat
                if tags.get('GPS GPSLongitudeRef') == 'W':
                    lon = -lon
                return lat, lon
        return None

    def convert_to_decimal(self, dms):
        """
        Konvertiert Grad, Minuten und Sekunden in Dezimalgrad.
        """
        return dms[0] + dms[1] / 60 + dms[2] / 3600
