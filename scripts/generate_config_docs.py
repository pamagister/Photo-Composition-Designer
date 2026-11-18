"""Generate a configuration reference from the typed settings defaults.

Replaces the old ``config_cli_gui``-based generator. The configuration system
is now the typed :class:`Settings` dataclass in
``photo_composition_designer.core.settings``; this script writes a Markdown
reference of the default values so the documentation stays in sync without a
runtime dependency on the removed config framework.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path

from photo_composition_designer.core.settings import Settings

DEFAULT_CONFIG_DOC = Path("docs/usage/config.md")


def _format_value(value: object) -> str:
    to_str = getattr(value, "to_str", None)
    if callable(to_str):
        return f"`{to_str()}`"
    return f"`{value!r}`"


def _walk(category: object, prefix: str, rows: list[tuple[str, str]]) -> None:
    for field in fields(category):  # type: ignore[arg-type]
        value = getattr(category, field.name)
        name = f"{prefix}{field.name}"
        if hasattr(value, "value"):
            rows.append((name, _format_value(value.value)))
        elif is_dataclass(value) and not isinstance(value, type):
            _walk(value, f"{name}.", rows)


def main() -> None:
    """Write the configuration reference Markdown file."""
    settings = Settings()
    rows: list[tuple[str, str]] = []
    _walk(settings, "", rows)

    lines = [
        "# Configuration reference",
        "",
        "Generated from `photo_composition_designer.core.settings.Settings` defaults.",
        "",
        "| Parameter | Default |",
        "| --- | --- |",
    ]
    for name, value in rows:
        lines.append(f"| `{name}` | {value} |")

    DEFAULT_CONFIG_DOC.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_CONFIG_DOC.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated: {DEFAULT_CONFIG_DOC}")


if __name__ == "__main__":
    main()