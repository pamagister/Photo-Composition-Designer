#!/usr/bin/env python3
"""Verify that a packaged release directory contains every runtime asset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

EXECUTABLE_NAMES = ("photo-composition-designer", "photo-composition-designer.exe")
REQUIRED_FILES = (
    "anniversaries.ini",
    "locations_en.ini",
    "locations_de.ini",
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
)
REQUIRED_DIRECTORIES = ("res", "docs", "images")


def find_missing_entries(release_dir: Path) -> list[str]:
    """Return the required release entries that are missing from ``release_dir``."""
    missing: list[str] = []
    if not any((release_dir / name).is_file() for name in EXECUTABLE_NAMES):
        missing.append(" or ".join(EXECUTABLE_NAMES))
    for name in REQUIRED_FILES:
        if not (release_dir / name).is_file():
            missing.append(name)
    for name in REQUIRED_DIRECTORIES:
        if not (release_dir / name).is_dir():
            missing.append(f"{name}/")
    return missing


def main(argv: list[str] | None = None) -> int:
    """Check one release directory and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_dir", type=Path, help="Packaged release directory.")
    args = parser.parse_args(argv)

    if not args.release_dir.is_dir():
        print(f"error: release directory does not exist: {args.release_dir}", file=sys.stderr)
        return 1

    missing = find_missing_entries(args.release_dir)
    if missing:
        print(f"error: {args.release_dir} is missing required entries:", file=sys.stderr)
        for entry in missing:
            print(f"  - {entry}", file=sys.stderr)
        return 1

    print(f"OK: {args.release_dir} contains all required release entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
