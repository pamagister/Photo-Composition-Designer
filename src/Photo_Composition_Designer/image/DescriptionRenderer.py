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

    # -------------------------------------------------------------------------

    def generate(self, text: str) -> Image.Image:
        """Render simple text label."""

        img = Image.new("RGB", (self.width_px, self.height_px), self.background_color)
        draw = ImageDraw.Draw(img)

        draw.text(
            (self.margin_side_px, self.height_px),
            text,
            fill=self.font.color.to_pil(),
            font=self.font.get_image_font(self.dpi),
            anchor="lb",
        )

        return img
