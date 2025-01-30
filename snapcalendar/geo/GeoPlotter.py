import math
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point


class GeoMapPlotter:
    """
    Class for plotting a map section with optional layers such as federal states or bodies of water.
    """

    def __init__(self, minimalExtension=5, resolution=(400, 300), background_color="white", border_color="black", line_width=1.0):
        """
        Initialisiert den GeoMapPlotter.
        :param minimalExtension: minimal extension in degrees for the map borders.
        :param resolution: Resolution of the map in pixels (width, height).
        :param background_color: Background color of the map.
        :param line_width: Line width for country and layer boundaries.
        """

        # Basisverzeichnis der shape files relativ zu diesem Modul
        base_path = Path(__file__).parent.parent.parent / "res/maps"

        countries_shp = base_path / "ne_50m_admin_0_countries/ne_50m_admin_0_countries.shp"  # Ländergrenzen
        lakes_shp = base_path / "ne_50m_rivers_lake_centerlines_scale_rank/ne_50m_rivers_lake_centerlines_scale_rank.shp"  # Flüsse und Seen

        self.shapefile_path = countries_shp
        self.minimalExtension = minimalExtension
        self.resolution = resolution
        self.background_color = self._normalize_color(background_color)
        self.border_color = self._normalize_color(border_color)
        self.line_width = line_width
        self.layers = {}

        # Zusätzliche Layer hinzufügen
        lakes_shp = Path(lakes_shp).resolve()
        self._addLayer("lakes", lakes_shp, color="royalblue", edgecolor="blue", alpha=1.0)

    @staticmethod
    def _normalize_color(color):
        """
        Normalizes the background color to the range 0-1, if necessary.
        :param color: Color as name, hex value or (R, G, B) tuple in the range 0-255.
        :return: Color in Matplotlib-compatible format.
        """
        if isinstance(color, tuple) and len(color) == 3:
            # Skaliere RGB-Werte von 0-255 auf 0-1
            return tuple(c / 255 for c in color)
        return color

    @staticmethod
    def _create_geodataframe(coords):
        """
        Creates a GeoDataFrame from GPS coordinates.
        :param coords: List of (latitude, longitude) tuples.
        :return: GeoDataFrame with points.
        """
        gdf = gpd.GeoDataFrame(
            {"geometry": [Point(lon, lat) for lat, lon in coords]},
            crs="EPSG:4326",
        )
        return gdf

    def _calculate_bounds(self, geo_df):
        """
        Calculates the boundaries of the map section with a buffer.
        :param geo_df: GeoDataFrame with points.
        :return: Boundaries as (minx, miny, maxx, maxy).
        """
        bounds = geo_df.total_bounds  # (minx, miny, maxx, maxy)

        # Calculate the height of the section based on the buffer

        height_deg = abs(bounds[3] - bounds[1]) / 2
        if height_deg < self.minimalExtension / 2:
            height_deg = self.minimalExtension / 2
        height_deg += self.minimalExtension / 8  # minimal margin

        # Calculate the average width (average width of the points in the GeoDataFrame)
        mid_lat = (bounds[1] + bounds[3]) / 2  # Average value of the miny and maxy coordinates (latitude)
        mid_lon = (bounds[0] + bounds[2]) / 2  # Average value of minx and maxx coordinates (longitude)

        lat_dis_per_deg = 111.32  # Spacing Latitude circle
        # Calculate the width of the section taking into account the latitude
        lon_dis_per_deg = lat_dis_per_deg * math.cos(math.radians(mid_lat))  # Longitude distance in km
        # Calculate the latitude based on the resolution and the actual longitude distance
        width_deg = 0.5 * lat_dis_per_deg * (height_deg + height_deg) * self.resolution[0] / self.resolution[1] / lon_dis_per_deg

        return (
            mid_lon - width_deg,
            mid_lat - height_deg,
            mid_lon + width_deg,
            mid_lat + height_deg,
        )

    def _addLayer(self, name, shapefile_path, color="blue", edgecolor="black", alpha=0.5):
        """
        Adds a layer such as federal states or bodies of water.

        :param name: Name of the layer.
        :param shapefile_path: Path to the shapefile of the layer.
        :param color: Fill color of the layer.
        :param edgecolor: Color of the edges.
        :param alpha: Transparency of the layer.
        """
        gdf = gpd.read_file(shapefile_path)
        self.layers[name] = {"gdf": gdf, "color": color, "edgecolor": edgecolor, "alpha": alpha}

    def renderMap(self, coords):
        """
        Creates a map section as a plotable object.
        :param coords: List of (latitude, longitude) tuples.
        :return: Plottable matplotlib.pyplot object.
        """
        # Shapefile für Ländergrenzen laden
        world = gpd.read_file(self.shapefile_path)
        location_markersize = 50

        # Kartengrenzen berechnen
        if not coords:
            points_gdf = self._create_geodataframe([(51.0504, 13.7373)])
            self.minimalExtension = 25
            bounds = self._calculate_bounds(points_gdf)
            location_markersize = 0
        else:
            # GeoDataFrame für GPS-Punkte erstellen
            points_gdf = self._create_geodataframe(coords)
            bounds = self._calculate_bounds(points_gdf)

        # Karte plotten
        fig, ax = plt.subplots(figsize=(self.resolution[0] / 100, self.resolution[1] / 100))
        fig.patch.set_facecolor(self.background_color)
        ax.set_facecolor(self.background_color)

        # Ländergrenzen plotten
        world.plot(ax=ax, color=self.background_color, edgecolor=self.border_color, linewidth=self.line_width * 1.0)

        # Zusätzliche Layer plotten - außer im großen Europa-Plot
        if coords:
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

        points_gdf.plot(ax=ax, color="red", markersize=location_markersize, label="GPS Points")

        # Set axes to the calculated limits
        ax.set_xlim(bounds[0], bounds[2])
        ax.set_ylim(bounds[1], bounds[3])

        # Achsen und Rand entfernen
        ax.axis("off")

        return plt


# Example call
if __name__ == "__main__":
    plotter = GeoMapPlotter(minimalExtension=4, resolution=(400, 400), background_color="white", line_width=1.0)

    # Coordinates:
    gps_coords = [
        (51.0504, 13.7373),  # Dresden
        (51.3397, 12.3731),  # Leipzig
        (50.8278, 12.9214),  # Chemnitz
        (51.1079, 17.0441),  # Breslau
        (52.5200, 13.5156),  # Berlin
    ]

    # locations = Locations()
    # gps_coords = list(locations.locations_dict.values())
    # Karte erstellen und anzeigen
    map_plt = plotter.renderMap(gps_coords)
    map_plt.show()

    # Karte erstellen ohne dass Koordinaten übergeben wurden.
    map_plt = plotter.renderMap([])
    map_plt.show()
