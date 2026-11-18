"""Package entry point for ``python -m photo_composition_designer``."""

from __future__ import annotations

import sys

from photo_composition_designer.cli.app import main

if __name__ == "__main__":
    sys.exit(main())
