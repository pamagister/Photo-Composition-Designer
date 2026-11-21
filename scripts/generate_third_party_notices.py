"""Generate THIRD_PARTY_NOTICES.md from runtime dependencies and bundled assets."""

from __future__ import annotations

import argparse
import re
from importlib import metadata
from pathlib import Path

import tomllib

DEFAULT_PYPROJECT = Path("pyproject.toml")
DEFAULT_OUTPUT = Path("THIRD_PARTY_NOTICES.md")
MAX_LICENSE_CHARS = 200_000

_LICENSE_FILE_RE = re.compile(r"(?i)(^|/)(licen[cs]e|copying|notice)(\.|_|$)")
_EXTRA_RE = re.compile(r"(?i)\bextra\s*==")
_REQUIREMENT_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")

HTMX_LICENSE = """Zero-Clause BSD

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE."""

TIM_WILSON_LICENSE = """MIT License

Copyright (c) 2020 Tim Wilson

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""


def _normalize(name: str) -> str:
    """Normalize a distribution name for de-duplication."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_name(requirement: str) -> str | None:
    """Return the distribution name from a requirement string."""
    match = _REQUIREMENT_NAME_RE.match(requirement)
    return match.group(1) if match else None


def _is_extra(requirement: str) -> bool:
    """Return whether a requirement is gated behind an extra."""
    return _EXTRA_RE.search(requirement) is not None


def _runtime_distributions(requirements: list[str]) -> list[metadata.Distribution]:
    """Return the installed runtime dependency closure for ``requirements``."""
    seen: set[str] = set()
    distributions: list[metadata.Distribution] = []

    def visit(requirement: str) -> None:
        if _is_extra(requirement):
            return
        name = _requirement_name(requirement)
        if name is None:
            return
        key = _normalize(name)
        if key in seen:
            return
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            return
        seen.add(key)
        distributions.append(distribution)
        for child in metadata.requires(name) or []:
            if not _is_extra(child):
                visit(child)

    for requirement in requirements:
        visit(requirement)

    return sorted(
        distributions,
        key=lambda distribution: _normalize(distribution.metadata.get("Name", "")),
    )


def _distribution_name(distribution: metadata.Distribution) -> str:
    """Return a display name for a distribution."""
    return distribution.metadata.get("Name", "unknown")


def _project_url(distribution: metadata.Distribution) -> str:
    """Return a useful upstream URL for a distribution."""
    home_page = distribution.metadata.get("Home-page")
    if home_page:
        return home_page.strip()
    for value in distribution.metadata.get_all("Project-URL") or []:
        label, separator, url = value.partition(",")
        if separator and label.strip().lower() in {"homepage", "repository", "source"}:
            return url.strip()
    return ""


def _license_summary(distribution: metadata.Distribution) -> str:
    """Return a short license label for a distribution."""
    expression = distribution.metadata.get("License-Expression")
    if expression:
        return expression.strip()
    license_text = distribution.metadata.get("License") or ""
    for line in license_text.splitlines():
        candidate = line.strip()
        if candidate:
            return candidate if len(candidate) <= 100 else candidate[:97] + "..."
    return "See license text"


def _license_files(distribution: metadata.Distribution) -> list[str]:
    """Return license-related files shipped by a distribution."""
    files: list[str] = []
    for file in distribution.files or []:
        path = str(file)
        if _LICENSE_FILE_RE.search(path):
            files.append(path)
    return files


def _read_license_file(distribution: metadata.Distribution, file: str) -> str:
    """Read one license file, truncating unusually large files."""
    path = Path(distribution.locate_file(file))
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if len(text) > MAX_LICENSE_CHARS:
        return text[:MAX_LICENSE_CHARS] + "\n... [truncated] ..."
    return text


def _fence(text: str) -> str:
    """Return a Markdown code fence that is safe for ``text``."""
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}text\n{text.rstrip()}\n{fence}"


def _render_dependency(distribution: metadata.Distribution) -> str:
    """Render one dependency and its license files as Markdown."""
    name = _distribution_name(distribution)
    lines = [
        f"### {name} {distribution.version}",
        "",
        f"- License: {_license_summary(distribution)}",
    ]
    source = _project_url(distribution)
    if source:
        lines.append(f"- Source: {source}")

    files = _license_files(distribution)
    if files:
        lines.append("- License files: " + ", ".join(f"`{file}`" for file in files))
        for file in files:
            text = _read_license_file(distribution, file)
            if text:
                lines.extend(["", f"#### `{file}`", "", _fence(text)])
    else:
        license_text = (distribution.metadata.get("License") or "").strip()
        if license_text and license_text != _license_summary(distribution):
            lines.extend(["", "#### License metadata", "", _fence(license_text)])

    return "\n".join(lines)


def _adapted_source_section() -> str:
    """Render attribution for adapted third-party source code."""
    return "\n".join(
        [
            "## Adapted source code",
            "",
            "### Collage algorithm",
            "",
            "- Copyright: 2020 Tim Wilson",
            "- Source: https://github.com/twilsonco/PyPhotoCollage",
            "- License: MIT",
            "",
            "Parts of the collage algorithm are adapted from PyPhotoCollage/PhotoCollage.py.",
            "",
            "#### License text",
            "",
            _fence(TIM_WILSON_LICENSE),
            "",
        ]
    )


def _bundled_assets_section() -> str:
    """Render bundled non-Python assets."""
    return "\n".join(
        [
            "## Bundled assets and media",
            "",
            "### Natural Earth map data",
            "",
            "- License: Public domain",
            "- Source: https://www.naturalearthdata.com/about/terms-of-use/",
            "- Files: `res/maps/`",
            "",
            "Natural Earth raster and vector map data are in the public domain. "
            "They may be used, modified and redistributed without permission.",
            "",
            "### htmx 2.0.4",
            "",
            "- License: 0BSD (Zero-Clause BSD)",
            "- Source: https://github.com/bigskysoftware/htmx/tree/v2.0.4",
            "- File: `src/photo_composition_designer/gui/static/htmx.min.js`",
            "",
            "#### License text",
            "",
            _fence(HTMX_LICENSE),
            "",
            "### Sample images",
            "",
            "- License: Pixabay Content License",
            "- Source: https://pixabay.com/service/license-summary/",
            "- Credits: `images/credits.md`",
            "",
        ]
    )


def _dependencies_section(distributions: list[metadata.Distribution]) -> str:
    """Render the runtime Python dependency section."""
    lines = [
        "## Runtime Python dependencies",
        "",
        "Generated from the project's runtime dependency closure.",
        "",
    ]
    if not distributions:
        lines.append("No runtime dependencies found.")
    for distribution in distributions:
        lines.extend([_render_dependency(distribution), ""])
    return "\n".join(lines)


def _optional_components_section() -> str:
    """Render optional and build-time components."""
    return "\n".join(
        [
            "## Optional and build-time components",
            "",
            "### YOLO object-detection model (not bundled)",
            "",
            "- License: AGPL-3.0",
            "- Source: https://github.com/ultralytics/ultralytics/blob/main/LICENSE",
            "",
            "The model is not part of this repository or the shipped application. "
            "Users can download it from the application settings. The development "
            "test fixture downloads it on demand and is skipped in non-interactive "
            "environments.",
            "",
            "### PyInstaller (build-time)",
            "",
            "- License: GPL-2.0 with Bootloader Exception",
            "- Source: https://pyinstaller.org/",
            "",
            "Used only to build the packaged executable; it is not a runtime "
            "dependency of the installed application.",
            "",
        ]
    )


def build_notices(pyproject_path: Path) -> str:
    """Build the complete third-party notices document."""
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    requirements = data.get("project", {}).get("dependencies", [])
    distributions = _runtime_distributions(requirements)
    header = "\n".join(
        [
            "<!-- Generated by scripts/generate_third_party_notices.py. Do not edit manually. -->",
            "",
            "# Third-Party Notices",
            "",
            "Photo-Composition-Designer is licensed under the MIT License. See `LICENSE`.",
            "",
            "Third-party components remain under their own licenses. This file "
            "lists bundled assets, runtime dependencies and optional build-time "
            "components.",
            "",
        ]
    )
    sections = [
        header,
        _adapted_source_section(),
        _bundled_assets_section(),
        _dependencies_section(distributions),
        _optional_components_section(),
    ]
    return "\n\n".join(section.strip() for section in sections) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the third-party notices file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pyproject", type=Path, default=DEFAULT_PYPROJECT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    content = build_notices(args.pyproject)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(content, encoding="utf-8")
    print(f"Generated: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
