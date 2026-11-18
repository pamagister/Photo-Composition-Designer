# Welcome to Photo-Composition-Designer

Photo-Composition-Designer is a local-first, browser-based calendar composition
editor. You create a project, point it at a directory of source photos, preview a
distribution of photos across calendar pages, curate each page by dragging photos
into slots, and export the result as a PDF.

[![Github CI Status](https://github.com/pamagister/Photo-Composition-Designer/actions/workflows/main.yml/badge.svg)](https://github.com/pamagister/Photo-Composition-Designer/actions)
[![License](https://img.shields.io/github/license/pamagister/Photo-Composition-Designer)](https://github.com/pamagister/Photo-Composition-Designer/blob/main/LICENSE)

## Features

* **Project-based workflow** – One central SQLite workspace holds every project,
  source root, photo inventory, page, layout and assignment.
* **Local web editor** – `uv run photo-composition-designer gui` opens a
  three-panel editor at `http://127.0.0.1:8767/`.
* **Source-relative photo references** – Originals are never moved, renamed or
  modified; a source root can be safely relinked if it moves.
* **GPS and local map** – EXIF GPS first, `locations.ini` filename fallback
  second, and a cached local map with a default point when no coordinates exist.
* **Versioned YAML layouts** – Curated slot layouts ship in the box; users can
  add their own `*.yaml` files without writing code.
* **Distribution proposals** – Equal, seeded-random and date-aware strategies
  preview without mutating state; applying is atomic.
* **Accessible editing** – Drag-and-drop with keyboard alternatives for every
  add, remove, replace and swap action.
* **Ordered export** – Render pages from project data and export a PDF that
  follows the project page order.

## Quick start

```bash
uv run photo-composition-designer gui
```

Then open `http://127.0.0.1:8767/`, create a project, add a source directory,
scan it, preview a distribution, and curate pages in the editor.

## Command-line

```
photo-composition-designer gui       # start the local web editor
photo-composition-designer scan      # reconcile a project's photo inventory
photo-composition-designer distribute  # preview or apply a distribution
photo-composition-designer render    # render a project's pages to PNG + PDF
photo-composition-designer export    # export a project as PDF
photo-composition-designer duplicate # copy a project within the workspace
photo-composition-designer doctor    # check workspace and project health
```

## Storage

The central workspace and caches live under the platform data directory:

```
~/.local/share/photo-composition-designer/
  workspace.sqlite3
  thumbnails/
  previews/
  cache/
  exports/
```

Environment overrides (`PCD_DATA_DIR`, `PCD_CACHE_DIR`) keep tests and portable
installs isolated.