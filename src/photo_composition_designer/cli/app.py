"""Command-line application for Photo Composition Designer.

Phase 1 provides a minimal argparse-based CLI so the package entry point
resolves and ``--help`` works. The full project-oriented command set
(``gui``, ``scan``, ``distribute``, ``render``, ``export``, ``doctor``) is
implemented in later phases; until then ``gui`` prints a placeholder message.
"""

from __future__ import annotations

import argparse
import sys

from photo_composition_designer.cli.commands import gui as gui_command


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="photo-composition-designer",
        description="Local-first calendar composition designer.",
    )
    subparsers = parser.add_subparsers(dest="command")

    gui_parser = subparsers.add_parser("gui", help="Start the local web editor.")
    gui_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind (default: 127.0.0.1).",
    )
    gui_parser.add_argument(
        "--port",
        type=int,
        default=8767,
        help="Port to listen on (default: 8767).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "gui":
        return gui_command.run(host=args.host, port=args.port)

    parser.print_help()
    return 0 if args.command is None else 1


if __name__ == "__main__":
    sys.exit(main())
