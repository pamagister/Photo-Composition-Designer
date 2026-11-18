"""Recursive image discovery for project source roots."""

from __future__ import annotations

import os
from pathlib import Path

#: File extensions treated as photos by the local editor.
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})


def find_image_files(root: Path, *, follow_symlinks: bool = False) -> list[Path]:
    """Return image files below ``root`` in deterministic relative-path order.

    Symbolic links are skipped by default so a project can never read outside
    its configured source root through a link.
    """
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"source directory does not exist: {root}")

    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        current = Path(dirpath)
        dirnames[:] = sorted(
            name for name in dirnames if follow_symlinks or not (current / name).is_symlink()
        )
        for filename in sorted(filenames):
            path = current / filename
            if path.is_symlink() and not follow_symlinks:
                continue
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                files.append(path)

    return sorted(files, key=lambda path: path.relative_to(root).as_posix())
