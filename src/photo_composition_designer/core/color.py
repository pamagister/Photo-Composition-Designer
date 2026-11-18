"""RGB color value type used by the rendering stack.

This replaces the ``config_cli_gui`` color type so the runtime no longer
depends on that package. The public shape (``to_pil``, ``to_hex``,
``from_hex``, ``to_list``) matches the old type so renderer code and tests
keep working unchanged.
"""

from __future__ import annotations


class Color:
    """Simple RGB color container."""

    def __init__(self, r: int = 0, g: int = 0, b: int = 0) -> None:
        self.r = max(0, min(255, r))
        self.g = max(0, min(255, g))
        self.b = max(0, min(255, b))

    def to_list(self) -> list[int]:
        """Return ``[r, g, b]``."""
        return [self.r, self.g, self.b]

    def to_rgb(self) -> tuple[float, float, float]:
        """Return normalized ``(r, g, b)`` floats in ``[0, 1]``."""
        return self.r / 255, self.g / 255, self.b / 255

    def to_pil(self) -> tuple[int, ...]:
        """Return a Pillow-compatible RGB tuple."""
        return tuple(int(c) for c in self.to_list())

    def to_hex(self) -> str:
        """Return ``#rrggbb``."""
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    @classmethod
    def from_list(cls, rgb_list: list[int | str]) -> Color:
        """Build from ``[r, g, b]``."""
        if len(rgb_list) >= 3:
            return cls(int(rgb_list[0]), int(rgb_list[1]), int(rgb_list[2]))
        return cls()

    @classmethod
    def from_hex(cls, hex_color: str) -> Color:
        """Build from ``#rrggbb`` or ``rrggbb``."""
        hex_color = hex_color.lstrip("#")
        if len(hex_color) == 6:
            return cls(
                int(hex_color[0:2], 16),
                int(hex_color[2:4], 16),
                int(hex_color[4:6], 16),
            )
        return cls()

    def __str__(self) -> str:
        return self.to_hex()

    def __repr__(self) -> str:
        return f"Color({self.r}, {self.g}, {self.b})"
