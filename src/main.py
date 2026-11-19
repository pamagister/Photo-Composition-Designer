"""PyInstaller entry point for the unified CLI/GUI executable."""

from __future__ import annotations

import sys

from photo_composition_designer.cli.app import main

if __name__ == "__main__":
    sys.exit(main())
