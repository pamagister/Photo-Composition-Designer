# Web UI Project Workflow Architecture

**Status:** Implemented
**Date:** 2026-11-18
**Plan:** `docs/plans/2026-11-18-web-ui-project-workflow.md`

This document records the implemented architecture of the project-based calendar
editor. It replaces the earlier Phase 0 design lock, which described the folder
workflow that has since been removed.

## 1. Purpose

The application is a local-first, browser-based calendar composition editor.
Projects, source roots, photo inventories, pages, layouts and slot assignments
are explicit persisted data. The renderer remains the source of truth for final
pages; the web UI and application services compose around it.

## 2. Layers

| Layer | Modules | Responsibility |
|---|---|---|
| Domain | `project/models.py`, `core/errors.py`, `core/output_profile.py` | Projects, source roots, photos, pages, layouts, slots, assignments, distribution proposals and the typed output profile. |
| Application services | `project/services.py`, `project/inventory.py`, `project/distribution.py`, `project/editing.py`, `project/rendering.py`, `io/export.py`, `io/project_archive.py` | Project lifecycle, scanning and relinking, distribution proposals, page editing, page composition inputs, export and reference-only archives. |
| Persistence | `db/schema.py`, `project/repositories.py` | SQLite schema, forward migrations and repositories. No SQL in routes or renderers. |
| Rendering | `render/page.py`, `render/slot_renderer.py`, `render/calendar.py`, `render/map.py`, `render/description.py`, `render/geoplot.py` | Full-page composition and the individual render features. |
| Infrastructure | `io/media.py`, `io/scan.py`, `io/previews.py`, `io/export.py`, `io/project_archive.py`, `core/settings.py` | Filesystem access, EXIF, Pillow adapters, caches, PDF output, reference-only project archives and project defaults. |
| Web UI | `gui/app.py`, `gui/routes/`, `gui/templates/`, `gui/static/` | FastAPI routes, Jinja templates, HTMX fragments and focused JavaScript. |
| CLI | `cli/app.py`, `cli/commands/` | Project-oriented commands for GUI, scanning, distribution, rendering, export, duplication and diagnostics. |

Route handlers validate input and call services. They contain no distribution
algorithms, GPS calculations, multi-table SQL or renderer geometry.

## 3. Storage

One central SQLite workspace stores all projects:

```text
~/.local/share/photo-composition-designer/
  workspace.sqlite3
  thumbnails/
  previews/
  cache/
  exports/
  layouts/
```

Global application preferences are stored under the platform configuration
directory, including the shared anniversary and location file paths.
`PCD_DATA_DIR`, `PCD_CACHE_DIR` and `PCD_CONFIG_DIR` override their platform
locations. The database is authoritative; thumbnails, page previews and exports
are disposable and rebuildable.

Schema version 4 contains `projects`, `source_roots`, `photos`, `layouts`,
`layout_slots`, `pages` (including the per-page `hide_local_map`,
`hide_calendar_strip` and `hide_description` overrides) and `assignments`.
Migrations are forward only. The connection enables WAL, foreign keys and a busy
timeout, and one application process is the deployment assumption.

Key invariants:

* A photo may be assigned to multiple slots; each slot on each page holds at
  most one photo (`UNIQUE(page_id, slot_id)`).
* A slot holds at most one photo (`UNIQUE(page_id, slot_id)`).
* Assignments cannot cross projects; triggers reject mismatched rows.
* The unused pool is derived from persisted assignments; there is no mutable
  `used` flag.
* Empty slots are valid and counts are reported explicitly.

## 4. Output profiles

`core/output_profile.py` defines a typed profile with five sections:

* **Calendar:** language, holiday countries, calendar toggle, orientation, short
  day/month names and title.
* **Style:** background colour and the four fonts with colour and size.
* **Geo:** map toggle, minimal extension and map dimensions.
* **Size:** page width/height, DPI, JPEG quality, calendar height and map size.
* **Layout:** margins, spacing, rounded corners, description toggle, image score
  factor and object recognition. Whether a PDF is written is chosen per export.

New projects snapshot the current `core/settings.py` defaults into
`projects.output_profile_json`. Existing projects with an empty snapshot receive a
stable read-time default without their rows being rewritten. Preview and export
read the project profile; workspace defaults only seed new projects. Saving
settings increments render revisions only when values actually change.

## 5. Rendering pipeline

1. `ProjectRenderingService.build_input` resolves the page, layout snapshot,
   assignments, photo paths, GPS coordinates and the project profile into a
   `PageRenderInput`.
2. `render/page.py` (`PageComposer`) composes the page: background, slot photos
   with per-assignment crop settings, local map, calendar strip below the photos,
   description and title. The first page is a title page when
   `calendar.use_title_page` is enabled; it always shows the composition title
   and defaults to hiding the map and description. Every page can override the
   global map, calendar-strip and description toggles with `hide_local_map`,
   `hide_calendar_strip` and `hide_description`. The application-wide anniversary
   file is supplied as a shared render input.
3. `render/slot_renderer.py` remains the slot compositing component.
4. `ProjectRenderingService.render_preview` renders a reduced-resolution JPEG and
   caches it under a key covering page revision, layout ID/version, profile hash,
   shared anniversary-file path/version, render mode and requested width.
5. `io/export.py` renders pages in explicit project order and writes JPG pages
   and/or a combined PDF, with export-time DPI and JPEG quality overrides.

The composer never queries SQLite or knows about FastAPI. The rendering service
is the only seam between persistence and rendering.

### Caching rules

* Thumbnails are keyed by photo ID, source modification time and size.
* Page previews are keyed by revision, layout version, profile hash, anniversary
  file version and width.
* A cached preview is served without re-rendering or decoding originals.
* Any edit increments the affected page's render revision; a profile change
  increments all affected pages.

## 6. Page editing

`project/editing.py` (`PageEditingService`) owns all page mutations:

* `assign_to_empty_slot`, `replace`, `swap` and `remove` enforce the slot
  uniqueness invariant and update the derived unused pool. Reusing the same
  photo in multiple slots is supported.
* `set_crop` stores zoom and focal point on the assignment. Source files are
  never modified.
* `set_description` updates the page description.
* `set_local_overrides` overrides the global map, calendar-strip and description
  toggles for one page.
* `plan_layout_change` maps existing assignments to the nearest normalized slot
  centers and reports preserved and displaced photos without mutating state.
* `change_layout` applies the same mapping transactionally, preserving
  assignments that fit and returning displaced photos to the pool.

Every mutation commits in one transaction, increments the page render revision
and refreshes the preview and unused-pool fragments. Adding or removing a photo
never changes the layout.

## 7. Distribution

`project/distribution.py` builds pure in-memory proposals with the `equal`,
`random` (seeded) and `date_aware` strategies. Proposals never mutate project
state or the filesystem. The web UI previews per-page samples, filled and empty
slots, overflow and the unassigned count, includes a proposal digest and applies
the reviewed proposal in one transaction. A stale digest is rejected and a
repeated confirmation is a no-op.

## 8. Sources and relinking

* Source roots store an absolute path; photos store POSIX-relative paths.
* Resolution is always `root / relative_path` with containment validation.
* A moved root is relinked through a preview that reports matched, ambiguous and
  missing basenames. Ambiguous basenames are never bound silently.
* Missing or unreadable files are marked unavailable without deleting
  assignments. Rescanning reconciles the inventory and keeps assignments.
* GPS precedence is EXIF, then the `locations.ini` filename fallback, then a
  deterministic default map point.

## 9. Web UI

The editor keeps three main areas:

* **Sidebar:** page thumbnails, dates and the active page.
* **Canvas:** rendered page preview, slot grid, layout change, crop, replace,
  move, remove and the page description.
* **Bottom panel:** horizontally scrolling photos, filtered to all or unused;
  repeated use is marked with a yellow warning indicator.

The Projects overview lists every project as a row with its own archive export,
duplication form and link into the editor. Project-level `.pcd` import/export and
duplication live there rather than inside a single project. The project toolbar's
**Extras** menu expands to the right and links to the `distribute` and `check`
subpages.

HTMX performs server-confirmed fragment swaps; focused JavaScript adds
drag-and-drop. Every drag action has a keyboard-visible equivalent. Layout change
previews displaced photos before confirmation. When a layout change would
displace photos the server requires an explicit confirmation.

Accessibility measures: skip link, labelled slots as groups, visible
`:focus-visible` outlines, labelled form controls, live status regions and a
stacked narrow-screen layout with a horizontal page strip. There are no drawers;
no control is hidden at narrow widths.

## 10. Export and portability

Reference-only export is the supported mode. `.pcd` archives contain project
metadata, page snapshots, assignments and source references, but never photo
files:

* Originals are never copied, moved, renamed or deleted.
* Another machine may require relinking the source root.
* The importer accepts a versioned archive manifest and does not extract paths
  from the archive.
* Browser image/PDF exports accept absolute local destinations and default to a
  project-specific folder under Pictures/Bilder when available. The export
  dialog selects JPG pages, a combined PDF or both, and may override the
  project's DPI and JPEG quality.

The browser export page and the CLI share `io/export.py`; both use the project
profile and explicit page order, and both report missing assets as actionable
warnings rather than producing silent partial output.

## 11. CLI

`photo-composition-designer` exposes `gui`, `scan`, `distribute`, `render`,
`export`, `duplicate` and `doctor`. Exit code `1` reports a failed operation;
`doctor` never modifies project data.

## 12. Testing

* Unit and service tests cover the database, repositories, scanning/relinking,
  distribution, editing, output profiles, page rendering, export, CLI and
  diagnostics.
* FastAPI `TestClient` tests cover routes, templates, fragments, redirects and
  error paths.
* `tests/test_browser_workflow.py` runs the critical flows (add, replace, move,
  remove, layout change, page navigation, export) against a real uvicorn server in
  Chromium and Firefox. The module skips when Playwright or the browser binaries
  are unavailable.
* `make lint` and `make test` are the local quality gate; Linux CI runs
  `make test`.

Verified on 2026-11-18: `make lint` clean, `make test` green.

## 13. Confirmed decisions

1. One central SQLite workspace database with multiple projects.
2. Reference-only `.pcd` archives; photo files are never embedded.
3. No legacy folder-calendar import.
4. Global versioned YAML layouts; existing page snapshots remain unchanged.
5. Photos may be reused across pages and slots.
6. Empty slots are valid; overflow stays unassigned.
7. Editable, persisted per-project output profiles.
8. Per-assignment crop and focal-point controls.
9. Editable, persisted page descriptions.
10. Deterministic layout changes with displaced-photo confirmation.
11. Local-only web application; Tkinter and `config-cli-gui` stay removed.

## 14. Known limitations and deferred work

* **No undo/redo:** every action is atomic and immediately persisted, but there is
  no bounded edit history. Implementing durable undo requires restoring page
  snapshots and resolving conflicts when a photo was reassigned elsewhere in the
  meantime; that complexity is deferred. Re-edit the affected page manually.
* **Reference-only archives:** moving sources requires relinking; photo files
  are intentionally not bundled.
* **Narrow screens:** panels stack instead of using drawers; drawers would add
  focus-trap and state complexity without a demonstrated need.
* **Single process:** no multi-user concurrency, distributed locking or remote
  hosting.
* **Layout editor:** slot geometry is entered as normalized JSON rather than
  manipulated with a visual drag/resize canvas.
* **Browser coverage in CI:** the Playwright suite is local-only by default; CI
  installs the Python dependency but not browser binaries, so the suite skips.
