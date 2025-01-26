from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point


class GeoMapPlotter:
    """
    Klasse zum Plotten eines Kartenausschnitts mit optionalen Layern wie Bundesländer oder Gewässer.
    """

    def __init__(self,
                 buffer_deg=2,
                 resolution=(400, 300),
                 background_color="white",
                 border_color="black",
                 line_width=1.0):
        """
        Initialisiert den GeoMapPlotter.
        :param buffer_deg: Zusätzliche Ausdehnung in Grad für die Kartengrenzen.
        :param resolution: Auflösung der Karte in Pixel (Breite, Höhe).
        :param background_color: Hintergrundfarbe der Karte.
        :param line_width: Linienbreite für Länder- und Layergrenzen.
        """

        # Basisverzeichnis relativ zur Datei geoPlotter.py
        base_path = Path(__file__).parent.parent.parent / "data/maps"

        countries_path = base_path / "ne_50m_admin_0_countries/ne_50m_admin_0_countries.shp"  # Ländergrenzen
        lakes_path = base_path / "ne_50m_rivers_lake_centerlines_scale_rank/ne_50m_rivers_lake_centerlines_scale_rank.shp"  # Flüsse und Seen

        self.shapefile_path = countries_path
        self.buffer_deg = buffer_deg
        self.resolution = resolution
        self.background_color = self._normalize_color(background_color)
        self.border_color = self._normalize_color(border_color)
        self.line_width = line_width
        self.layers = {}

        # Zusätzliche Layer hinzufügen
        lakes_path = Path(lakes_path).resolve()
        self.add_layer("lakes", lakes_path, color="blue", edgecolor="blue", alpha=1.0)

    @staticmethod
    def _normalize_color(color):
        """
        Normalisiert die Hintergrundfarbe in den Bereich 0-1, falls nötig.
        :param color: Farbe als Name, Hex-Wert oder (R, G, B)-Tupel im Bereich 0-255.
        :return: Farbe im Matplotlib-kompatiblen Format.
        """
        if isinstance(color, tuple) and len(color) == 3:
            # Skaliere RGB-Werte von 0-255 auf 0-1
            return tuple(c / 255 for c in color)
        return color

    @staticmethod
    def _create_geodataframe(coords):
        """
        Erstellt ein GeoDataFrame aus GPS-Koordinaten.
        :param coords: Liste von (Breitengrad, Längengrad)-Tupeln.
        :return: GeoDataFrame mit Punkten.
        """
        return gpd.GeoDataFrame(
            {"geometry": [Point(lon, lat) for lat, lon in coords]},
            crs="EPSG:4326",
        )

    def _calculate_bounds(self, geo_df):
        """
        Berechnet die Grenzen des Kartenausschnitts mit einem Puffer.
        :param geo_df: GeoDataFrame mit Punkten.
        :return: Begrenzungen als (minx, miny, maxx, maxy).
        """
        bounds = geo_df.total_bounds  # (minx, miny, maxx, maxy)
        return (
            bounds[0] - self.buffer_deg*1,  # minx - Puffer
            bounds[1] - self.buffer_deg,  # miny - Puffer
            bounds[2] + self.buffer_deg*1,  # maxx + Puffer
            bounds[3] + self.buffer_deg,  # maxy + Puffer
        )

    def add_layer(self, name, shapefile_path, color="blue", edgecolor="black", alpha=0.5):
        """
        Fügt einen zusätzlichen Layer wie Bundesländer oder Gewässer hinzu.
        :param name: Name des Layers.
        :param shapefile_path: Pfad zum Shapefile des Layers.
        :param color: Füllfarbe des Layers.
        :param edgecolor: Farbe der Ränder.
        :param alpha: Transparenz des Layers.
        """
        gdf = gpd.read_file(shapefile_path)
        self.layers[name] = {"gdf": gdf, "color": color, "edgecolor": edgecolor, "alpha": alpha}

    def render_map(self, coords):
        """
        Erstellt einen Kartenausschnitt als plottbares Objekt.
        :param coords: Liste von (Breitengrad, Längengrad)-Tupeln.
        :return: Plottbares matplotlib.pyplot-Objekt.
        """
        # Shapefile für Ländergrenzen laden
        world = gpd.read_file(self.shapefile_path)

        # GeoDataFrame für die GPS-Punkte erstellen
        points_gdf = self._create_geodataframe(coords)

        # Kartengrenzen berechnen
        bounds = self._calculate_bounds(points_gdf)

        # Karte plotten
        fig, ax = plt.subplots(figsize=(self.resolution[0] / 100, self.resolution[1] / 100))
        fig.patch.set_facecolor(self.background_color)
        ax.set_facecolor(self.background_color)

        # Ländergrenzen plotten
        world.plot(ax=ax, color=self.background_color, edgecolor=self.border_color, linewidth=self.line_width*1.5)

        # Zusätzliche Layer plotten
        for layer_name, layer_data in self.layers.items():
            layer_data["gdf"].plot(
                ax=ax,
                markersize=20,
                color=layer_data["color"],
                edgecolor=layer_data["edgecolor"],
                alpha=layer_data["alpha"],
                linewidth=self.line_width,
                label=layer_name,
            )

        # GPS-Punkte plotten
        points_gdf.plot(ax=ax, color="red", markersize=50, label="GPS Points")

        # Achsen auf die berechneten Grenzen setzen
        ax.set_xlim(bounds[0], bounds[2])
        ax.set_ylim(bounds[1], bounds[3])

        # Achsen und Rand entfernen
        ax.axis("off")

        return plt


# Beispielaufruf
if __name__ == "__main__":
    # Plotter initialisieren
    plotter = GeoMapPlotter(buffer_deg=2, resolution=(400, 300), background_color="lightgray", line_width=0.8)

    # Koordinaten: Dresden, Leipzig, Chemnitz
    gps_coords = [
        (51.0504, 13.7373),  # Dresden
        (51.3397, 12.3731),  # Leipzig
        (50.8278, 12.9214),  # Chemnitz
    ]

    # Karte erstellen und anzeigen
    plt = plotter.render_map(gps_coords)
    plt.show()
