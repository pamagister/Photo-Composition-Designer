import exifread
from PIL import Image

from snapcalendar.common.config import Config
from snapcalendar.geo.geoPlotter import GeoMapPlotter


class MapGenerator:

    def __init__(self):
        self.config = Config()
        self.height = self.config.calendarHeight

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
            resolution=(self.height, self.height),
            background_color=self.config.backgroundColor,
            border_color=self.config.textColor1)

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