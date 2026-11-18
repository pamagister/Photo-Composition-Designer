# Web UI Project Workflow Architecture

**Status:** Phase 0 design lock
**Date:** 2026-11-18
**Plan:** `docs/plans/2026-11-18-web-ui-project-workflow.md`

This document records the Phase 0 baseline and the architecture decisions that
must be stable before the Phase 1 database implementation starts. It is an
architecture decision record, not user documentation for the new workflow.

## 1. Purpose

The refactoring replaces folder-driven calendar generation with a local,
project-based editor. The renderer stays the source of truth for final pages;
projects, source references and assignments become explicit persisted data.

## 2. Current implementation baseline

### 2.1 Rendering stack

| Component | Location | Responsibility |
|---|---|---|
| `CompositionRendererBuilder` | `core/composition_builder.py:47-139` | Derives DPI and millimetre-to-pixel page dimensions; constructs the complete render dependency graph. |
| `CompositionLayout` | `core/composition_layout.py:12-73` | Page geometry, available collage area and description tag parsing. |
| `CompositionPageRenderer` | `core/composition_renderer.py:33-171` | Renders a page from photos, a date and a description: background, calendar, map, description, collage and date text. |
| `CollageRenderer` | `image/CollageRenderer.py:95-715` | Chooses a collage pattern, partitions image sizes and places/crops images. Accepts an injected object detector. |
| `CompositionDesignerFactory` | `application/composition_designer_factory.py:24-60` | Wires `CompositionIO` and render components into `CompositionDesigner`. |
| `CalendarRenderer` | `image/CalendarRenderer.py:32-444` | Horizontal/vertical calendar grids, holidays, sun and moon symbols. |
| `MapRenderer`, `DescriptionRenderer`, `ObjectDetector`, `SmartCrop` | `image/` | Supporting render features that must keep working. |

The renderer is decoupled from storage through `CompositionRenderContext` and
the `CompositionFileOperations` protocol (`core/composition_io.py:17-34`).
`CompositionDesignerFactory.create()` accepts injected `file_io` and
`render_components`, which is the safe seam for project-based rendering.

### 2.2 Folder-coupled composition

`CompositionDesigner` (`core/base.py:32-220`) assumes one subfolder is one page:

- `get_photo_folders()` returns sorted subdirectory names (`core/composition_io.py:79-81`).
- `week_index` is the position of the folder name in the sorted list (`core/base.py:158,204`).
- Page date is derived only from position: `startDate + timedelta(weeks=week_index)` (`core/base.py:185`).
- The first folder is the title page (`core/base.py:101-104,188`).
- Descriptions come from a `.txt` file inside the folder, falling back to a positional global description (`core/base.py:178-183`).
- Output is fixed to `photo_dir.parent / "collages"`, files named `{folder_name}.jpg` (`core/base.py:53,206`) and `output.pdf` (`core/composition_io.py:98-127`).

These assumptions are the part the new workflow must replace. The rendering
components below them do not need to be rewritten.

### 2.3 Physical distribution

`PhotoDistributionWorkflow.distribute()` (`application/photo_distribution_workflow.py:29-74`)
copies photos into dated folders such as `01_Jan-01` inside the source tree.
`ImageDistributor` (`tools/ImageDistributor.py`) provides equal, deterministic
random (seed 11) and date-aware strategies. `distribute_by_week` exists but is
not called by the workflow. The refactor extracts these algorithms into a pure
proposal service and stops creating folders.

### 2.4 Configuration and output settings

`ConfigParameterManager` (`config/config.py:280-303`) defines six categories:

- General: source directory, anniversary/location INI paths, composition title.
- Calendar: `useCalendar`, language, holiday countries, start date, page count, orientation.
- Style: background colour and four fonts (family, size, colour).
- Geo: map usage and minimum degree range.
- Size: page width/height in mm, calendar/map heights, DPI, JPEG quality.
- Layout: margins, spacing, rounded corners, image score factor, short names, description toggle, PDF toggle, object recognition.

There is no explicit print-provider or bleed model in the code. Dimensions are
millimetres converted to pixels at the configured DPI. Margins and spacing act
as the effective safe area. Typography is the `Font` values. For this project,
an **output profile** is the complete snapshot of calendar, style, geo, size and
layout settings that affect rendering. Every project must store its own snapshot
so later workspace-default changes cannot alter an existing project.

### 2.5 GUI and CLI

- Tkinter `MainGui` (`gui/gui.py:43-899`) coordinates four phases: configuration, distribution, description file generation, and composition/export. Long operations run on daemon threads with progress callbacks.
- CLI `main()` (`cli/cli.py:80-101`) loads config, builds `CompositionWorkflow` through `CompositionApplicationFactory`, and generates collages plus `output.pdf`.
- Entry points: `Photo-Composition-Designer` (CLI) and `Photo-Composition-Designer-gui` (`pyproject.toml:49-51`).

The new local web application replaces the Tkinter surface. The CLI is replaced
by project-oriented commands in Phase 9.

### 2.6 Test coverage map

| Area | Tests |
|---|---|
| Folder-driven designer and descriptions | `test_CompositionDesigner.py` |
| Workflow modes, preview scaling, real render/PDF, distribution copying | `test_application_workflows.py` |
| Distribution algorithms | `test_ImageDistributor.py` |
| CLI end-to-end | `test_cli.py` |
| File operations and renderer wiring | `test_composition_components.py` |
| Collage, calendar, map, description rendering | `test_CollageRenderer.py`, `test_CalendarRenderer.py`, `test_MapRenderer.py`, `test_DescriptionRenderer.py` |
| Object detection and smart crop | `test_ObjectDetector.py`, `test_SmartCrop.py` |
| Photo/EXIF/date/GPS helpers | `test_Photo.py` |
| Map plotting | `test_GeoPlotter.py` |
| Calendar support data | `test_anniversaries.py`, `test_Locations.py`, `test_MoonPhase.py` |

The new project workflow needs its own tests; the existing tests remain the
regression baseline for rendering behavior.

## 3. Image Triage reference patterns

Image Triage is available locally at `/home/paul/PycharmProjects/image-triage`.
Only its local-web-app patterns are reusable; its photo-rating domain is not.

| Pattern | Reference | Reuse decision |
|---|---|---|
| FastAPI app factory, `/static` mount, request-scoped repository, `/health` | `src/image_triage/gui/app.py:576-599` | Reuse structure. |
| Jinja2 `base.html` with `title`/`head`/`content` blocks | `src/image_triage/gui/templates/base.html:1-32` | Reuse structure. |
| HTMX partial updates | Bundled but unused; Image Triage uses vanilla `fetch()` JSON endpoints plus full-page navigation (`app.py:892-1036`, `templates/compare.html:87-104`) | Use HTMX for server-rendered fragments as planned; fall back to focused JavaScript for drag-and-drop. |
| Static CSS with `:root` custom properties and component classes | `src/image_triage/gui/static/style.css:1-1919` | Reuse conventions, not the domain styles. |
| Controlled media endpoints with `is_relative_to(root)` validation and cache headers | `app.py:181-191,1732-1754` | Reuse the security pattern. |
| SQLite connection with WAL, foreign keys, busy timeout, schema version table and forward migrations | `db/schema.py:226-258`, `db/migrate.py:20-122` | Reuse the migration approach. |
| Repository class with `open()`, context manager, `commit`/`rollback` | `db/repository.py:100-126` | Reuse layering. |
| TestClient fixtures with isolated app data directory | `tests/conftest.py:10-56`, `tests/test_gui.py` | Reuse test structure. |
| Packaging with GUI entry point and package data | `pyproject.toml:39-44,76-82` | Reuse packaging approach. |

## 4. Architecture decisions

### 4.1 Layers

- **Domain:** project, source root, photo asset, calendar page, layout, slot, assignment and distribution proposal models.
- **Application services:** project lifecycle, scanning/relinking, distribution, page editing, rendering and export.
- **Persistence:** SQLite schema, migrations and repositories. No SQL in routes or renderers.
- **Infrastructure:** filesystem access, thumbnail/preview cache and Pillow adapters.
- **Web UI (Phase 6+):** FastAPI routes, Jinja templates, HTMX fragments and focused JavaScript.

### 4.2 Workspace storage

One central SQLite workspace database is the normal store:

```text
~/.local/share/photo-composition-designer/
  workspace.sqlite3
  thumbnails/
  previews/
  cache/
  exports/
```

Use an XDG-aware/platformdirs data location. Cache and preview files are
disposable and rebuildable; only the database and project assets are
authoritative.

### 4.3 Project portability

A project is a logical aggregate in the workspace database, not a separate live
file. Portability uses a versioned `.pcd` ZIP archive containing a manifest, a
project-only SQLite snapshot, immutable layout snapshots and optional assets.
Export uses a consistent snapshot, never the live workspace database. Import
validates the manifest and schema version, stages assets, resolves duplicate
project IDs explicitly and inserts in one transaction.

Reference-only is the default. Self-contained export copies originals into
`assets/` on explicit request, never moves them, and verifies integrity.

### 4.4 Image identity and references

- Store a canonical source-root path and each photo path relative to it, using normalized POSIX separators.
- Never rely on an absolute per-photo path.
- Store file size and mtime; use a content digest only when a stronger identity check is needed.
- Resolve `root / relative_path`, validate containment, and mark missing or unreadable files unavailable without deleting records.
- Relinking is an explicit, previewed operation. It reports matched, missing and ambiguous files and never silently binds a record to a same-basename file.

### 4.5 Relational model

Logical tables: `projects`, `source_roots`, `photos`, `pages`, `layouts`,
`layout_slots`, `assignments`, and optional `project_assets`.

- All project-owned rows are scoped by `project_id`; repositories prevent cross-project assignments.
- A photo is assigned at most once per project; a slot holds at most one photo. Both are enforced by unique constraints.
- The unassigned pool is derived by querying photos that have no assignment. No persisted `used` flag.
- Layout definitions contain no photo identities; assignments contain no duplicated geometry.
- Persist an immutable layout snapshot/version with each page so application updates cannot silently change its appearance.

### 4.6 Layout schema and page capacity

A layout has a stable ID/version and named slots with normalized geometry
(0..1), dimensions, z-order and crop defaults. Slot geometry is converted to
pixels using the project page dimensions and DPI. Each layout has a fixed slot
count; empty slots are valid and overflow photos stay unassigned. Initial layouts
must be at least as broad as the existing collage patterns. Manual layout
authoring is deferred.

### 4.7 Project settings snapshot

Every project snapshots all output-affecting values: calendar, style, geo, size
and layout settings listed in section 2.4, plus provider dimensions/scaling,
margins, typography, JPEG quality and render options. Workspace defaults only
seed new projects.

### 4.8 Compatibility

No import of existing folder-based calendars is required. Preserve provider
sizing/scaling, the existing layout catalogue and render features. Keep a
compatibility adapter for the existing CLI/renderer paths until Phase 9, then
remove Tkinter and `config-cli-gui` from runtime dependencies.

### 4.9 Web stack and directory selection

FastAPI + Jinja2 + HTMX + vanilla JavaScript, local-only. No SPA framework.

The source-directory picker is **deferred to Phase 6** per the user decision:
Phase 0-2 must not introduce a web UI. The persistence and scanning services
must accept a validated absolute path so any future UI can call them without
schema changes.

### 4.10 Caching and concurrency

One application process is the deployment assumption. Configure SQLite foreign
keys, WAL, busy timeout and explicit transaction boundaries. Generate thumbnails
once and cache page previews by page render revision plus render settings. Every
edit commits transactionally and increments the page render revision.

## 5. Confirmed decisions

1. One central SQLite workspace database with multiple projects.
2. Portable `.pcd` ZIP archives with manifest, project snapshot and optional assets.
3. Reference-only default; self-contained export is explicit and verified.
4. No legacy folder-calendar import; preserve provider sizing and existing layout catalogue.
5. Fixed slots; empty slots valid; overflow stays unassigned.
6. One photo use per project; duplicates are distinct assets.
7. Editable, persisted page descriptions.
8. Fixed layout templates first; manual layout authoring deferred.
9. Per-assignment crop/focal-point controls without modifying originals.
10. Local-only web application; remove Tkinter and `config-cli-gui`; project-oriented CLI.

## 6. Deferred or unresolved

- **Source-directory picker:** deferred to Phase 6. Phase 0-2 use a validated path parameter only.
- **Exact layout catalogue:** inventory existing patterns in Phase 4 and document any deliberate additions.
- **Undo/redo depth:** decide in Phase 5; minimum is atomic, recoverable edit operations.

## 7. Baseline verification

Run on 2026-11-18, branch `plan/web-ui-calendar-project-workflow`, before any
Phase 1 implementation:

```text
make test
```

Result:

- Ruff lint and format checks passed.
- 106 pytest tests passed.
- Coverage report generated (64% total; existing gaps are the untested Tkinter
  GUI and packaging entry points).

CI on the feature branch was made to run for every branch push and completed
successfully (`e17c6e6`). No pre-existing test failures were found.

## 8. Phase gates

- Phase 1 starts only after the storage, page model and compatibility decisions in this document are accepted.
- Phase 2 starts only after domain and persistence APIs are stable.
- Phase 3 starts only after source inventory and path resolution are stable.