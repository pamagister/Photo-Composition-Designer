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
| Application services | `project/services.py`, `project/inventory.py`, `project/distribution.py`, `project/editing.py`, `project/rendering.py`, `io/export.py` | Project lifecycle, scanning and relinking, distribution proposals, page editing, page composition inputs and export. |
| Persistence | `db/schema.py`, `project/repositories.py` | SQLite schema, forward migrations and repositories. No SQL in routes or renderers. |
| Rendering | `render/page.py`, `render/slot_renderer.py`, `render/calendar.py`, `render/map.py`, `render/description.py`, `render/geoplot.py` | Full-page composition and the individual render features. |
| Infrastructure | `io/media.py`, `io/scan.py`, `io/previews.py`, `io/export.py`, `core/settings.py` | Filesystem access, EXIF, Pillow adapters, caches, PDF output and the defaults used to seed new projects. |
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
```

`PCD_DATA_DIR` and `PCD_CACHE_DIR` override the platform locations. The database
is authoritative; thumbnails, page previews and exports are disposable and
rebuildable.

Schema version 1 contains `projects`, `source_roots`, `photos`, `layouts`,
`layout_slots`, `pages` and `assignments`. Migrations are forward only. The
connection enables WAL, foreign keys and a busy timeout, and one application
process is the deployment assumption.

Key invariants:

* A photo is assigned at most once per project (`UNIQUE(project_id, photo_id)`).
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
* **Size:** page width/height, DPI, JPEG quality and calendar/map heights.
* **Layout:** margins, spacing, rounded corners, description and PDF toggles,
  image score factor and object recognition.

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
   with per-assignment crop settings, calendar strip, local map, description,
   anniversaries and title. The first page is treated as the title page.
3. `render/slot_renderer.py` remains the slot compositing component.
4. `ProjectRenderingService.render_preview` renders a reduced-resolution JPEG and
   caches it under a key covering page revision, layout ID/version, profile hash,
   render mode and requested width.
5. `io/export.py` renders pages in explicit project order and writes PNG pages
   plus a combined PDF.

The composer never queries SQLite or knows about FastAPI. The rendering service
is the only seam between persistence and rendering.

### Caching rules

* Thumbnails are keyed by photo ID, source modification time and size.
* Page previews are keyed by revision, layout version, profile hash and width.
* A cached preview is served without re-rendering or decoding originals.
* Any edit increments the affected page's render revision; a profile change
  increments all affected pages.

## 6. Page editing

`project/editing.py` (`PageEditingService`) owns all page mutations:

* `assign_to_empty_slot`, `replace`, `swap` and `remove` enforce the uniqueness
  invariants and return photos to the derived unused pool.
* `set_crop` stores zoom and focal point on the assignment. Source files are
  never modified.
* `set_description` updates the page description.
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

The editor keeps three areas:

* **Sidebar:** page thumbnails, dates and the active page.
* **Canvas:** rendered page preview, slot grid, layout change, crop, replace,
  move, remove and the page description.
* **Bottom panel:** unused photos with counts.

HTMX performs server-confirmed fragment swaps; focused JavaScript adds
drag-and-drop. Every drag action has a keyboard-visible equivalent. Layout change
previews displaced photos before confirmation. When a layout change would
displace photos the server requires an explicit confirmation.

Accessibility measures: skip link, labelled slots as groups, visible
`:focus-visible` outlines, labelled form controls, live status regions and a
stacked narrow-screen layout with a horizontal page strip. There are no drawers;
no control is hidden at narrow widths.

## 10. Export and portability

Reference-only export is the supported mode. Pages reference source photos
through remappable roots:

* Originals are never copied, moved, renamed or deleted.
* Another machine may require relinking the source root.
* Self-contained `.pcd` archives and embedded assets are deferred and not
  partially implemented.

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
2. Reference-only export; `.pcd` archives and embedded assets deferred.
3. No legacy folder-calendar import.
4. Fixed YAML layout templates; manual layout authoring deferred.
5. One photo use per project; duplicates are distinct assets.
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
* **Reference-only export:** moving sources requires relinking; no portable
  project archive exists yet.
* **Narrow screens:** panels stack instead of using drawers; drawers would add
  focus-trap and state complexity without a demonstrated need.
* **Single process:** no multi-user concurrency, distributed locking or remote
  hosting.
* **Layout catalogue:** curated YAML layouts only; no visual layout editor.
* **Browser coverage in CI:** the Playwright suite is local-only by default; CI
  installs the Python dependency but not browser binaries, so the suite skips.
