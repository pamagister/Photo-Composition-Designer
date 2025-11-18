import geopandas as gpd
import pytest
from pyogrio.errors import DataSourceError
from shapely.geometry import Point

from Photo_Composition_Designer.tools.GeoPlotter import GeoPlotter


@pytest.fixture
def geo_plotter():
    """Erzeugt eine Instanz von GeoPlotter für Tests."""
    return GeoPlotter()


def test__normalize_color(geo_plotter):
    """Testet die Normalisierung von Farben."""
    assert geo_plotter._normalize_color("red") == "red"
    assert geo_plotter._normalize_color("#00FF00") == "#00FF00"
    assert geo_plotter._normalize_color((255, 0, 0)) == (1.0, 0.0, 0.0)
    assert all(
        abs(a - b) < 0.01
        for a, b in zip(geo_plotter._normalize_color((128, 128, 128)), (0.5, 0.5, 0.5))
    )


def test__create_geodataframe(geo_plotter):
    """Testet die Erstellung eines GeoDataFrame aus GPS-Koordinaten."""
    coordinates = [(51.0504, 13.7373), (52.5200, 13.4050)]  # Dresden, Berlin
    gdf = geo_plotter._create_geodataframe(coordinates)

    assert isinstance(gdf, gpd.GeoDataFrame)
    assert len(gdf) == 2
    assert gdf.geometry.iloc[0] == Point(13.7373, 51.0504)  # Lon, Lat
    assert gdf.geometry.iloc[1] == Point(13.4050, 52.5200)


def test__calculate_bounds(geo_plotter):
    """Testet die Berechnung der Kartengrenzen."""
    coordinates = [(51.0504, 13.7373), (52.5200, 13.4050)]  # Dresden, Berlin
    gdf = geo_plotter._create_geodataframe(coordinates)
    bounds = geo_plotter._calculate_bounds(gdf)

    assert len(bounds) == 4
    assert bounds[0] < bounds[2]  # minx < maxx
    assert bounds[1] < bounds[3]  # miny < maxy


def test__add_layer(geo_plotter):
    """Testet das Hinzufügen eines Layers."""
    with pytest.raises(DataSourceError):  # Fehler erwartet, weil keine gültige Datei vorhanden ist
        geo_plotter._addLayer("test_layer", "invalid/path/to/shapefile.shp")

    # Wenn ein echtes Shapefile verwendet wird, könnte man prüfen,
    # ob es in `geo_plotter.layers` existiert.


def test_render_map(geo_plotter):
    """Testet die Generierung einer Karte mit Matplotlib."""
    coordinates = [(51.0504, 13.7373), (52.5200, 13.4050)]
    plt_obj = geo_plotter.renderMap(coordinates)

    assert plt_obj.figure().dpi == 100  # Prüft, ob eine matplotlib-Figur zurückgegeben wird
