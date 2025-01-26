import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point


class GeoMapPlotter:
    """
    Klasse zum Plotten eines Kartenausschnitts mit optionalen Layern wie Bundesländer oder Gewässer.
    """

    def __init__(self, buffer_km=100, resolution=(500, 600)):
        """
        Initialisiert den GeoMapPlotter.
        :param shapefile_path: Pfad zum Shapefile mit Ländergrenzen.
        :param buffer_km: Puffer in Kilometern um die äußersten Punkte.
        :param resolution: Auflösung der Karte in Pixel (Breite, Höhe).
        """

        countries_path = "../../data/maps/ne_50m_admin_0_countries/ne_50m_admin_0_countries.shp"   # Path to the shapefile for country borders
        lakes_path = "../../data/maps/ne_50m_rivers_lake_centerlines_scale_rank/ne_50m_rivers_lake_centerlines_scale_rank.shp"  # Rivers and lakes

        self.shapefile_path = countries_path
        self.buffer_km = buffer_km
        self.resolution = resolution
        self.layers = {}

        # Add additional layers
        self.add_layer("lakes", lakes_path, color="blue", edgecolor="blue", alpha=0.5)

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

    @staticmethod
    def _calculate_bounds(geo_df, buffer_km):
        """
        Berechnet die Grenzen des Kartenausschnitts mit einem Puffer.
        :param geo_df: GeoDataFrame mit Punkten.
        :param buffer_km: Puffer in Kilometern.
        :return: Begrenzungen als (minx, miny, maxx, maxy).
        """
        buffer_degrees = buffer_km / 111  # 1 Breitengrad ≈ 111 km
        bounds = geo_df.total_bounds  # (minx, miny, maxx, maxy)
        return (
            bounds[0] - buffer_degrees,  # minx - Puffer
            bounds[1] - buffer_degrees,  # miny - Puffer
            bounds[2] + buffer_degrees,  # maxx + Puffer
            bounds[3] + buffer_degrees,  # maxy + Puffer
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

    def plot_map(self, coords):
        """
        Plottet den Kartenausschnitt.
        :param coords: Liste von (Breitengrad, Längengrad)-Tupeln.
        :param title: Titel des Plots.
        """
        # Shapefile für Ländergrenzen laden
        world = gpd.read_file(self.shapefile_path)

        # GeoDataFrame für die GPS-Punkte erstellen
        points_gdf = self._create_geodataframe(coords)

        # Kartengrenzen berechnen
        bounds = self._calculate_bounds(points_gdf, self.buffer_km)

        # Karte plotten
        fig, ax = plt.subplots(figsize=(self.resolution[0] / 100, self.resolution[1] / 100))
        world.plot(ax=ax, color="white", edgecolor="black")

        # Zusätzliche Layer plotten
        for layer_name, layer_data in self.layers.items():
            layer_data["gdf"].plot(
                ax=ax,
                markersize=20,
                color=layer_data["color"],
                edgecolor=layer_data["edgecolor"],
                alpha=layer_data["alpha"],
                label=layer_name,
            )

        # GPS-Punkte plotten
        points_gdf.plot(ax=ax, color="red", markersize=50, label="GPS Points")

        # Achsen auf die berechneten Grenzen setzen
        ax.set_xlim(bounds[0], bounds[2])
        ax.set_ylim(bounds[1], bounds[3])

        plt.show()


# Beispielaufruf
if __name__ == "__main__":

    # Plotter initialisieren
    plotter = GeoMapPlotter(buffer_km=400, resolution=(400, 300))


    # Koordinaten: Dresden, Leipzig, Chemnitz
    gps_coords = [
        (51.0504, 13.7373),  # Dresden
        (51.3397, 12.3731),  # Leipzig
        (50.8278, 12.9214),  # Chemnitz
    ]

    # Karte plotten
    plotter.plot_map(gps_coords)
