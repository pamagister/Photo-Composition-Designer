from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.tools.GeoPlotter import GeoPlotter
from Photo_Composition_Designer.tools.Helpers import mm_to_px


class MapRenderer:
    def __init__(
        self,
        mapHeight: int,
        mapWidth: int,
        minimalExtension: int,
        backgroundColor: tuple[int, int, int],
        textColor1: tuple[int, int, int],
    ):
        self.height = mapHeight
        self.width = mapWidth
        self.minimalExtension = minimalExtension
        self.backgroundColor = backgroundColor
        self.textColor1 = textColor1

    @classmethod
    def from_config(cls, config: ConfigParameterManager) -> MapRenderer:
        """Creates a MapRenderer from a ConfigParameterManager instance."""
        map_height_px = mm_to_px(config.size.mapHeight.value, config.size.dpi.value)
        map_width_px = mm_to_px(config.size.mapWidth.value, config.size.dpi.value)

        return cls(
            mapHeight=map_height_px,
            mapWidth=map_width_px,
            minimalExtension=config.geo.minimalExtension.value,
            backgroundColor=config.style.backgroundColor.value.to_pil(),
            textColor1=config.style.fontLarge.value.color.to_pil(),
        )

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
        map_generator = MapRenderer(size, size, 7, (30, 30, 30), (150, 250, 150))

        img = map_generator.generate(gps_coordinates)

        map_plt.paste(img)
        map_plt.save(temp_dir / f"map_{size}.jpg")
