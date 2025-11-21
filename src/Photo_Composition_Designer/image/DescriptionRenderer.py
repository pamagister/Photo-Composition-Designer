from __future__ import annotations

from PIL import Image, ImageDraw

from Photo_Composition_Designer.config.config import ConfigParameterManager
from Photo_Composition_Designer.tools.Helpers import load_font, mm_to_px


class DescriptionRenderer:
    def __init__(
        self,
        width_px: int,
        font_size: int,
        spacing_px: int,
        margin_side_px: int,
        background_color,
        text_color,
    ):
        self.width_px = int(width_px)
        self.spacing_px = int(spacing_px)
        self.font_size = int(font_size)
        self.margin_side_px = int(margin_side_px)
        self.background_color = background_color
        self.text_color = text_color

        # Height includes bottom spacing from your original code
        self.height_px = self.font_size + self.spacing_px

    # -------------------------------------------------------------------------

    @classmethod
    def from_config(cls, config: ConfigParameterManager) -> DescriptionRenderer:
        width_px = mm_to_px(config.size.width.value, config.size.dpi.value)
        spacing_px = mm_to_px(config.layout.spacing.value, config.size.dpi.value)
        margin_side_px = mm_to_px(config.layout.marginSides.value, config.size.dpi.value)

        font_size = int(
            config.layout.fontSizeSmall.value
            * config.size.calendarHeight.value
            * config.size.dpi.value
            / 25.4
        )

        bg = config.colors.backgroundColor.value.to_pil()
        text_color = config.colors.textColor2.value.to_pil()

        return cls(
            width_px=width_px,
            font_size=font_size,
            spacing_px=spacing_px,
            margin_side_px=margin_side_px,
            background_color=bg,
            text_color=text_color,
        )

    # -------------------------------------------------------------------------

    def generate(self, text: str) -> Image.Image:
        """Render simple text label."""

        img = Image.new("RGB", (self.width_px, self.height_px), self.background_color)
        draw = ImageDraw.Draw(img)

        font = load_font(size=self.font_size)

        draw.text(
            (self.margin_side_px, self.height_px),
            text,
            fill=self.text_color,
            font=font,
            anchor="lb",
        )

        return img
