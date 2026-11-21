"""GUI-first process launcher for Photo Composition Designer."""

from __future__ import annotations

import sys

from photo_composition_designer.cli.app import cli_main
from photo_composition_designer.cli.commands import gui as gui_command


def main() -> int:
    """Start the web UI by default, or the CLI when arguments are provided."""
    if len(sys.argv) > 1:
        return cli_main()
    return gui_command.run()


if __name__ == "__main__":
    sys.exit(main())
