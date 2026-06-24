from __future__ import annotations

from config_cli_gui.configtypes.font import Font
from PIL import Image, ImageDraw

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.tools.Helpers import mm_to_px


class DescriptionRenderer:
    def __init__(
        self,
        width_px: int,
        font: Font,
        spacing_px: int,
        margin_side_px: int,
        background_color,
        dpi: int,
    ):
        self.width_px = int(width_px)
        self.spacing_px = int(spacing_px)
        self.font = font
        self.margin_side_px = int(margin_side_px)
        self.background_color = background_color
        self.dpi = dpi

        # Height includes bottom spacing from your original code
        self.height_px = int(self.font.size * self.dpi / 25.4 + self.spacing_px)

    # -------------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: ConfigParameterManager) -> DescriptionRenderer:
        """Creates a DescriptionRenderer from a ConfigParameterManager instance."""
        width_px = mm_to_px(config.size.width.value, config.size.dpi.value)
        spacing_px = mm_to_px(config.layout.spacing.value, config.size.dpi.value)
        margin_side_px = mm_to_px(config.layout.marginSides.value, config.size.dpi.value)

        return cls(
            width_px=width_px,
            font=config.style.fontDescription.value,
            spacing_px=spacing_px,
            margin_side_px=margin_side_px,
            background_color=config.style.backgroundColor.value.to_pil(),
            dpi=config.size.dpi.value,
        )

    def generate(self, description: str, alignment="middle") -> Image.Image:
        """Generates an image with the given description text."""
        img = Image.new("RGBA", (self.width_px, self.height_px), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Use the font object to get the PIL font with the correct DPI
        pil_font = self.font.get_image_font(self.dpi)

        if alignment == "left":
            text_x = self.margin_side_px
            anchor = "lb"
        elif alignment == "middle":
            text_x = self.width_px / 2
            anchor = "mb"
        else:  # right
            text_x = self.width_px
            anchor = "rb"

        text_y = self.height_px

        draw.text(
            (text_x, text_y),
            description,
            font=pil_font,
            fill=(*self.font.color.to_pil(), 255),
            anchor=anchor,
        )
        return img
