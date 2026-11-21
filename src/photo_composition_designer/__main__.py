"""Package entry point for ``python -m photo_composition_designer``."""

from __future__ import annotations

import sys

from photo_composition_designer.launcher import main

if __name__ == "__main__":
    sys.exit(main())
