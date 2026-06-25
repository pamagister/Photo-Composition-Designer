# scripts/update_readme.py
from pathlib import Path

src = Path("docs/index.md")
dst = Path("README.md")

# Optional: prepend a note that it's generated
prefix = "<!-- This README.md is auto-generated from docs/index.md -->\n\n"

# Lese die Quelldatei explizit mit UTF-8 Kodierung
source_content = src.read_text(encoding="utf-8")

# Schreibe den Inhalt in die Zieldatei, ebenfalls mit UTF-8 Kodierung
dst.write_text(
    prefix
    + source_content.replace(r"](getting-started/", r"](docs/getting-started/").replace(
        r"](_static/", r"](docs/_static/").replace(
        r"](funding/", r"](docs/funding/").replace(
        r"](getting-started/", r"](docs/getting-started/").replace(
        r"](usage/", r"](docs/usage/"),
    encoding="utf-8",
)
print(f"DONE    -  {dst} updated from {src}")
