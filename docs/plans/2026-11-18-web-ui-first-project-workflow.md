# Web UI First: Project-Based Calendar Editor

**Status:** Planning baseline  
**Created:** 2026-11-18  
**Repository:** `pamagister/Photo-Composition-Designer`  
**Reference implementation:** `pamagister/image-triage`  
**Execution mode:** autopilot, with phase-boundary handoffs and explicit user decisions where required

## 1. Objective and desired outcome

Refactor Photo-Composition-Designer into a local-first, browser-based calendar editor.
The web UI is the primary product surface and is delivered before any further
backend-only convenience work. The final product starts with:

```bash
uv run photo-composition-designer gui
```

and opens `http://127.0.0.1:8767/` by default.

The application must preserve the existing composition and rendering quality while
replacing the folder-driven workflow with explicit projects, pages, source references
and slot assignments. The UI must feel fast, local and editor-like, following the
proven stack and interaction patterns from `image-triage`: FastAPI, Jinja2, HTMX,
vanilla JavaScript, hand-written CSS and SQLite repositories.

The default editor shell has three areas:

- a side panel listing all calendar pages/collages with thumbnails;
- a main canvas showing the selected page, its slot targets and page actions;
- a bottom panel listing all unused/unassigned photos, with search, sort and counts.

The backend logic is part of the product, not an afterthought. In particular, image
inventory, EXIF/date/GPS extraction, source-relative identity, the small local map,
layout snapshots, distribution, render previews and export must remain correct and
testable without the browser.

## 2. Scope, constraints and explicit non-goals

### Mandatory scope

- Replace the Tkinter interaction surface with a local FastAPI web application.
- Provide a single project-oriented CLI with `gui` as the primary subcommand.
- Restructure `src/` to follow the `image-triage` package layout.
- Remove Tkinter, `ttkbootstrap`, `config-cli-gui` and the old config/dialog workflow
  from the runtime path.
- Use one central SQLite workspace with multiple projects and versioned migrations.
- Keep source-relative photo references, metadata, availability and safe relinking.
- Keep GPS behavior: EXIF first, `locations.ini` filename fallback second, deterministic
  local map with a default map point when no coordinates exist.
- Keep the small map local and cached; no external tile service.
- Model page composition as versioned layouts with named slots.
- Ship the existing sensible collage/calendar patterns as compact, user-editable YAML
  layouts. Users can add their own layouts without a separate layout authoring UI.
- Implement project creation/open/save, recursive scanning, distribution proposals,
  page editing, preview rendering and ordered PDF export.
- Deliver accessible drag-and-drop with keyboard alternatives.
- Update all relevant tests, run configurations, Makefile targets and documentation.

### Explicit constraints

- Original source photos are read-only. Never move, rename, delete or modify them.
- No intermediate per-page/per-week photo folders in the new workflow.
- Adding a photo never changes the current layout.
- The unassigned pool is derived from persisted assignments, not from a mutable flag.
- One photo can be assigned at most once per project.
- A slot holds at most one photo; empty slots are valid.
- The old folder-based CLI compatibility is not required.
- The renderer remains the source of truth for final pages and PDF output.
- The web application is local-first. Do not add cloud services or runtime network maps.
- Code, documentation, plans and comments are in English.
- Use `uv`, `pytest`, `ruff`, 4-space indentation and a 100-character line limit.

### Non-goals

- Multi-user accounts, cloud synchronization or remote hosting.
- A general-purpose photo manager or rating tool.
- Rewriting Pillow/collage rendering without evidence that the adapter is insufficient.
- Editing original pixels or destructive source-file operations.
- Manual free-form vector layout authoring. YAML files are the extension point.
- Legacy folder-calendar import. Existing render behavior must be preserved, not the old
  folder workflow.
- Interactive browser maps or third-party map tiles.

## 3. Repository findings and reference patterns

### 3.1 Current baseline to preserve

The existing renderer is already separated enough to reuse:

- `CompositionRendererBuilder` wires DPI, page geometry and rendering collaborators.
- `CompositionLayout` calculates page/collage dimensions and parses description flags.
- `CompositionPageRenderer` renders a full page from photos, a date and a description.
- `CollageRenderer` performs pattern selection, weighting, splitting, cropping and placement.
- `CalendarRenderer`, `MapRenderer`, `DescriptionRenderer`, `ObjectDetector` and
  `SmartCrop` provide the calendar, GPS map, text, object detection and smart crop.
- `ImageDistributor` contains equal, deterministic-random and date-aware strategies.
- `Photo` extracts EXIF date/GPS and filename/date fallbacks.

The folder coupling lives above this rendering stack:

- `CompositionIO.get_photo_folders()` discovers subdirectories.
- `CompositionDesigner` treats folder order as page order and derives dates/descriptions
  from it.
- `PhotoDistributionWorkflow` physically copies photos into generated folders.
- The Tkinter GUI coordinates configuration, distribution, preview and generation.

The refactor replaces those couplings with explicit project/page/assignment data. It
must not rewrite the renderer wholesale.

### 3.2 Existing Phase 0/1 work

Phase 0 and Phase 1 of `docs/plans/2026-11-18-web-ui-project-workflow.md` are already
implemented:

- typed project/source/photo/page/layout/assignment models;
- central SQLite schema, repositories, constraints and lifecycle services;
- 23 project tests, with the previous suite reported green at 129 tests.

This plan keeps that domain/persistence foundation and moves the web application and
its UX/backend integration ahead of all remaining backend-only phases.

### 3.3 image-triage patterns to adopt

| Pattern | Reference | Decision |
|---|---|---|
| Package layout | `src/image_triage/{cli,core,db,gui,io,...}` | Mirror with `photo_composition_designer`. |
| Typer CLI | `src/image_triage/cli/app.py` | Use one CLI app and a `gui` command. |
| FastAPI factory | `src/image_triage/gui/app.py` | Use an app factory, static mount, request lifecycle and health endpoint. |
| Jinja base template | `src/image_triage/gui/templates/base.html` | Use semantic blocks, header nav and server-rendered pages. |
| HTMX and focused JS | `gui/static/*.js`, templates | Use HTMX for fragments, vanilla JS for drag/drop and client-only affordances. |
| CSS conventions | `gui/static/style.css` | Reuse token-based, compact, high-contrast component styling. |
| Media safety | `_media_path`, `is_relative_to` checks | Serve only resolved project/source assets and cached previews. |
| SQLite setup | `db/schema.py`, `db/migrate.py` | Keep WAL, foreign keys, busy timeout, versioned forward migrations. |
| Repository layering | `db/repository.py` | Keep SQL out of routes and renderers. |
| TestClient fixtures | `tests/conftest.py`, `tests/test_gui.py` | Isolate appdata/cache and test routes through FastAPI TestClient. |
| Appdata isolation | `core/appdata.py` | Use XDG-aware config/data/cache paths with environment overrides. |

The Pixabay collection in `image-triage/images/pixabay` is the local demo/test fixture
source. The old images under `images/title`, `images/week_*` and `images/descriptions.txt`
are discarded. The replacement images are copied flat into this repository's `images/`.

## 4. Architecture and decisions

### 4.1 Target source layout

Restructure `src/` to mirror image-triage conventions:

```text
src/
  photo_composition_designer/
    __init__.py
    __main__.py
    cli/
      app.py
      commands/
        gui.py
        scan.py
        distribute.py
        render.py
        export.py
        doctor.py
    core/
      appdata.py
      errors.py
      models.py
      settings.py
      geometry.py
    db/
      schema.py
      migrate.py
      repository.py
    io/
      scan.py
      media.py
      previews.py
      pdf.py
    layouts/
      catalog.py
      loader.py
      layouts/*.yaml
    render/
      builder.py
      collage.py
      page.py
      calendar.py
      description.py
      map.py
      object_detector.py
      smart_crop.py
      geoplot.py
    project/
      models.py
      repositories.py
      services.py
      distribution.py
      rendering.py
      export.py
    gui/
      app.py
      routes/
        projects.py
        editor.py
        media.py
        jobs.py
      templates/
        base.html
        projects.html
        editor.html
        partials/*.html
      static/
        style.css
        editor.js
        htmx.min.js
```

The old `Photo_Composition_Designer` package, `src/main.py`, `src/firewall_handler.py`,
`src/path_handler.py`, `config_cli_gui` configuration classes and Tkinter modules are
removed from the runtime path. Any retained compatibility helpers must be justified and
covered by tests.

### 4.2 Layers

- **Domain:** project, source root, photo asset, page, layout, slot, assignment and
  distribution proposal models.
- **Application services:** project lifecycle, scanning/relinking, distribution,
  editing, rendering, map generation and export.
- **Persistence:** SQLite schema, migrations and repositories. No SQL in routes.
- **Infrastructure:** filesystem access, EXIF/Pillow adapters, local map shapefiles,
  thumbnail/preview cache, PDF writer.
- **Web UI:** FastAPI routes, Jinja templates, HTMX fragments and focused JavaScript.

Route handlers validate input and call services. They must not contain distribution
algorithms, GPS calculations, multi-table SQL or renderer geometry.

### 4.3 Workspace storage and portability

Keep the Phase 1 model:

```text
~/.local/share/photo-composition-designer/
  workspace.sqlite3
  thumbnails/
  previews/
  cache/
  exports/
```

Use an XDG-aware/platformdirs data location. Cache and preview files are disposable.
A `.pcd` ZIP archive remains the portable project format with manifest, project-only
SQLite snapshot, immutable layout snapshots and optional assets.

Reference-only is the default. Self-contained export is explicit, staged, verified and
never moves originals.

### 4.4 Image inventory and GPS

- Store source-root path and POSIX-relative photo paths.
- Resolve photos only as `root / relative_path` with containment validation.
- Preserve relative-path identity when files move via explicit relinking.
- Extract dimensions, capture date and GPS using the existing `Photo`/EXIF behavior.
- GPS precedence remains: EXIF GPS first, then `locations.ini` filename fallback.
- Missing coordinates are allowed. The local map then uses the established default point
  and a wider map extension.
- Never silently bind an ambiguous basename to a different file during relinking.
- Mark missing/unreadable files unavailable without deleting assignments.

### 4.5 Local map and rendering

The small map remains a server-side, cached render:

- Coordinates for a page/project are aggregated from assigned photos.
- The map cache key includes coordinate set, map dimensions, DPI, colors, minimal
  extension and the local shapefile version.
- No Leaflet, OSM tiles or runtime network access is introduced.
- `GeoPlotter`/`MapRenderer` behavior is preserved but moved behind a service adapter.
- The map is cached as PNG and served through a controlled media endpoint.
- Page previews are cached by page render revision plus render settings.

### 4.6 Layout catalogue

Model layouts as versioned slot templates:

```yaml
key: three_portrait_landscape
version: 1
name: "One portrait, two landscapes"
slots:
  - key: portrait
    x: 0.0
    y: 0.0
    width: 0.5
    height: 1.0
    crop_mode: cover
  - key: landscape_top
    x: 0.5
    y: 0.0
    width: 0.5
    height: 0.5
  - key: landscape_bottom
    x: 0.5
    y: 0.5
    width: 0.5
    height: 0.5
```

- Ship the existing sensible collage patterns as compact YAML files.
- Do not expose every internal pattern variant; curate a user-friendly catalogue.
- Users can add YAML files in the user layout directory without writing code.
- Validate bounds, unique slot keys, unique positions, positive dimensions and crop modes.
- Copy selected layout definitions into immutable per-page snapshots.
- Later application changes must not silently alter an existing project's page layout.

### 4.7 Distribution

Refactor equal, deterministic-random and date-aware distribution into a pure proposal
service:

`DistributionProposal(pages, unassigned, warnings, strategy, seed)`

- The proposal does not mutate project state or the filesystem.
- The UI previews per-page samples, counts, empty slots and overflow.
- Applying a proposal replaces initial assignments in one transaction.
- Random distribution persists its seed and strategy.
- Overflow stays unassigned; empty slots are reported, not silently discarded.

### 4.8 Page editing

- Drag an unassigned photo onto an empty slot to assign it.
- Drag onto an occupied slot requires explicit replace semantics; replaced photos return
  to the unused pool.
- Drag one assigned photo onto another assigned slot to swap.
- Remove clears the slot and returns the photo to the unused pool.
- Adding/removing never changes the layout.
- Layout changes preserve assignments where possible and preview displaced photos.
- Crop/focal-point controls are assignment properties, not source mutations.
- Every edit commits transactionally and increments the page render revision.

### 4.9 Web UI and interaction model

Default editor shell:

```text
+------------------------------------------------------------------+
| header: project name, save state, page actions, export           |
+----------------+----------------------------------+--------------+
| side panel     | main canvas                      | optional     |
| all pages /    | selected page, slots, calendar,  | details /    |
| collages       | map, description, page controls  | page info    |
+----------------+----------------------------------+--------------+
| bottom panel: all unused images, search/sort/count               |
+------------------------------------------------------------------+
```

- Side panel: page thumbnails, dates, assigned counts and active-page state.
- Bottom panel: all unused images, with search and sort.
- Main canvas: rendered current-page preview with visible slot/drop affordances.
- Optional details panel: page metadata, crop controls, assignment details or warnings.
- Desktop/laptop is the primary target. Narrow screens may collapse panels into drawers.
- Prefer server-confirmed updates; use optimistic UI only when rollback is reliable.
- Provide keyboard-accessible add/remove/replace/swap actions for every drag/drop flow.

### 4.10 Configuration

Replace `config.yaml`/`config-cli-gui` with typed settings similar to image-triage:

- central defaults in appdata;
- project snapshots for all output-affecting values;
- GUI host/port defaults (`127.0.0.1:8767`);
- local data/cache paths;
- layout directories;
- map/render/cache options.

The old provider dimensions, DPI, margins, typography and calendar settings are migrated
as named project defaults. They are not retained as a runtime dependency on
`config-cli-gui`.

## 5. Phase plan

Work packages are dependency ordered. Each package should be reviewable, testable and
committable on its own. Update the Progress / Handoff block at every phase boundary.
Do not implement multiple phases in one change.

## Phase 0: Repository baseline, image fixture replacement and design lock

**Objective:** Establish the new baseline before moving code.

- [ ] **P0-W01:** Replace the old image fixture set: remove `images/title`,
  `images/week_1` through `images/week_8_testimages_5` and `images/descriptions.txt`;
  copy all images from `/home/paul/PycharmProjects/image-triage/images/pixabay/` flat
  into `images/`.
- [ ] **P0-W02:** Update `.gitignore`, test fixtures and documentation references so the
  old folder structure is no longer part of the repository contract.
- [ ] **P0-W03:** Inventory existing tests and map them to renderer, project, map,
  distribution, CLI and GUI responsibilities.
- [ ] **P0-W04:** Record baseline verification commands and current test status before
  restructuring.
- [ ] **P0-W05:** Confirm the target package layout, runtime settings and removal list for
  Tkinter, `config-cli-gui`, `ttkbootstrap`, `src/main.py` and the old run configurations.

**Acceptance criteria**

- `images/` contains the Pixabay collection flat and no old week/title images.
- The repository baseline and test status are documented.
- The removal and restructuring list is explicit.

**Phase gate:** Do not move rendering code until the fixture replacement and baseline are
committed and verified.

## Phase 1: Source restructuring and project foundation migration

**Objective:** Move the existing project foundation into the new package layout without
changing its public behavior.

- [ ] **P1-W01:** Create `src/photo_composition_designer/` with the target subpackages.
- [ ] **P1-W02:** Move project models, DB, migrations, repositories and services from
  `src/Photo_Composition_Designer/project/`; update imports and packaging.
- [ ] **P1-W03:** Move reusable rendering modules into `render/` and preserve behavior
  through existing regression tests.
- [ ] **P1-W04:** Add typed core models/settings and XDG-aware appdata paths.
- [ ] **P1-W05:** Update `pyproject.toml`, `Makefile`, `.idea/runConfigurations` and docs
  generation for the new package and entry points.
- [ ] **P1-W06:** Remove obsolete Tkinter/config modules and their dependencies from the
  runtime path.

**Acceptance criteria**

- All existing project/renderer tests pass under the new package path.
- No production module imports `Photo_Composition_Designer`, `config_cli_gui` or Tkinter.
- Packaging exposes `photo-composition-designer = "photo_composition_designer.cli.app:main"`.
- Run configurations and documentation commands use the new package.

**Phase gate:** The new package layout and domain APIs are stable before adding the web UI.

## Phase 2: Web application foundation and project lifecycle

**Objective:** Deliver the first usable browser application.

- [ ] **P2-W01:** Add FastAPI application factory, static files, Jinja base template,
  health endpoint and appdata/settings lifecycle.
- [ ] **P2-W02:** Implement the single Typer CLI and `gui` command with default
  `http://127.0.0.1:8767/`.
- [ ] **P2-W03:** Add project selection/open/create workflow and visible save state.
- [ ] **P2-W04:** Add a safe local-only source-directory chooser or validated path entry.
- [ ] **P2-W05:** Add source scanning, scan progress/summary, missing-source state and
  actionable errors.
- [ ] **P2-W06:** Add server-side routes and HTMX partials for project, inventory and page
  navigation.
- [ ] **P2-W07:** Add controlled thumbnail/media endpoints with content types and cache
  headers.
- [ ] **P2-W08:** Add FastAPI TestClient tests with isolated appdata and temporary source
  directories.

**Acceptance criteria**

- `uv run photo-composition-designer gui` starts the local web app.
- A user can create/open a project and scan a source directory.
- The server never exposes arbitrary filesystem paths.
- UI actions call application services and contain no business logic in route handlers.

**Phase gate:** Project creation and source inventory are usable in the browser before
building the full editor.

## Phase 3: Image inventory, GPS extraction and local map

**Objective:** Make source photos, metadata and the small map correct and testable.

- [ ] **P3-W01:** Implement recursive image discovery with explicit extensions,
  deterministic ordering and symlink policy.
- [ ] **P3-W02:** Extract metadata using the existing `Photo`/EXIF behavior; persist
  dimensions, capture date, GPS, size, mtime and availability.
- [ ] **P3-W03:** Implement rescan/reconcile: add new files, detect changed files, mark
  missing files and retain project history.
- [ ] **P3-W04:** Implement safe source resolution and path traversal protection.
- [ ] **P3-W05:** Implement source-root remapping with preview, match counts, ambiguity
  handling and atomic confirmation.
- [ ] **P3-W06:** Preserve GPS precedence: EXIF first, `locations.ini` fallback second,
  deterministic default map when no coordinates are available.
- [ ] **P3-W07:** Extract the local map service and cache generated map PNGs by coordinate
  set, geometry, colors, DPI and shapefile version.
- [ ] **P3-W08:** Add tests for EXIF/no-EXIF, filename location fallback, no GPS,
  duplicate basenames, unreadable files, traversal attempts and map cache keys.

**Acceptance criteria**

- Scanning creates inventory records without copying or moving source images.
- A moved source root cannot silently relink an ambiguous basename.
- The small map is local, cached and deterministic.
- GPS fallback and default-map behavior are covered by regression tests.

**Phase gate:** Inventory, GPS and map behavior are stable before distribution and editor
assignment work.

## Phase 4: Layout catalogue and slot-based rendering

**Objective:** Decouple layouts from photos while preserving render quality.

- [ ] **P4-W01:** Define and validate the compact versioned YAML layout format.
- [ ] **P4-W02:** Ship curated layouts covering the existing sensible collage patterns.
- [ ] **P4-W03:** Implement YAML discovery from built-in and user layout directories.
- [ ] **P4-W04:** Implement layout validation: bounds, overlap policy, minimum size,
  unique keys and crop modes.
- [ ] **P4-W05:** Introduce a slot-aware renderer adapter over the existing page/collage
  renderer.
- [ ] **P4-W06:** Adapt page rendering to explicit page date, description, layout snapshot
  and assignments instead of folder names.
- [ ] **P4-W07:** Preserve calendar, anniversary, map, description, object detection and
  smart-crop behavior through regression tests.
- [ ] **P4-W08:** Add deterministic preview fixtures for representative page layouts.

**Acceptance criteria**

- A page renders from explicit project data without a page folder.
- Layout YAML contains no photo identities.
- Existing render features remain functional or have documented accepted differences.
- A later application update cannot silently alter a saved page's layout snapshot.

**Phase gate:** Rendering from project data is visually and functionally equivalent for
supported features.

## Phase 5: Distribution proposals and page editing services

**Objective:** Implement complete non-UI editing behavior.

- [ ] **P5-W01:** Extract equal, deterministic-random and date-aware distribution into a
  pure proposal service.
- [ ] **P5-W02:** Define behavior for N pages, insufficient images, overflow, unknown
  dates and capacity limits.
- [ ] **P5-W03:** Persist random seed and strategy metadata for reproducible proposals.
- [ ] **P5-W04:** Add proposal summaries and preview data.
- [ ] **P5-W05:** Implement atomic apply/replace of proposals.
- [ ] **P5-W06:** Implement add-to-empty-slot, remove, replace and swap operations.
- [ ] **P5-W07:** Derive the unused pool from inventory and current assignments.
- [ ] **P5-W08:** Implement layout changes with deterministic slot mapping and displaced
  photo handling.
- [ ] **P5-W09:** Implement per-assignment crop/focal-point overrides.
- [ ] **P5-W10:** Increment page render revisions and invalidate only affected previews.
- [ ] **P5-W11:** Add transactional tests for swaps, replacements, removals, duplicate
  assignment rejection, layout changes and rollback.

**Acceptance criteria**

- Distribution never creates intermediate folders or copies source images.
- Previewing a proposal does not mutate project state.
- Every photo is either assigned once or appears in the unused pool.
- Adding a photo never changes a layout.
- Failed operations leave page and pool state unchanged.

**Phase gate:** All editing rules are enforceable by services, not only UI conventions.

## Phase 6: Calendar editor UI and three-panel interaction model

**Objective:** Deliver the central editing experience.

- [ ] **P6-W01:** Build the three-area shell: page/collage side panel, main canvas and
  bottom unused-image panel.
- [ ] **P6-W02:** Render the selected page with visible slot boundaries and assignment
  affordances.
- [ ] **P6-W03:** Implement accessible drag-and-drop from unused images to empty slots.
- [ ] **P6-W04:** Implement drag-and-drop replace and swap behavior.
- [ ] **P6-W05:** Add explicit remove actions and immediate unused-pool updates.
- [ ] **P6-W06:** Add layout selection with confirmation for displaced photos.
- [ ] **P6-W07:** Add search, sort and efficient loading for the unused-image panel.
- [ ] **P6-W08:** Add page navigation, status indicators, save feedback and responsive
  panel behavior.
- [ ] **P6-W09:** Add keyboard-accessible alternatives for every drag-and-drop action.
- [ ] **P6-W10:** Add browser-level tests for add, replace, swap, remove, layout change and
  page navigation.

**Acceptance criteria**

- The requested three-panel editor works without reloading the whole application.
- The unused pool always reflects persisted assignments.
- Page thumbnails and current-page previews reflect committed changes.
- Core editing remains possible without a mouse.
- Desktop/laptop is the primary target; narrow-screen behavior is explicit.

**Phase gate:** A user can curate a full calendar from the browser.

## Phase 7: Guided project creation, distribution preview and rendering

**Objective:** Make project setup and visual verification end-to-end.

- [ ] **P7-W01:** Build the new-project workflow for name, calendar settings, page count,
  source directory and layout defaults.
- [ ] **P7-W02:** Add distribution strategy/seed selection and preview before commit.
- [ ] **P7-W03:** Show per-page thumbnail samples, photo counts, empty slots and overflow.
- [ ] **P7-W04:** Allow regenerating a proposal without saving until confirmation.
- [ ] **P7-W05:** Add render preview jobs and progress for the selected page.
- [ ] **P7-W06:** Add full-project preview rendering with ordered page results.
- [ ] **P7-W07:** Add tests for cancel/revise/confirm proposal behavior and render
  revision invalidation.

**Acceptance criteria**

- New projects can be created without intermediate folders.
- The user sees distribution and page previews before applying them.
- Cancelling leaves no partial assignments or copied files.
- Initial page count and dates are explicit and persisted.

**Phase gate:** New-project setup and rendering are repeatable end-to-end.

## Phase 8: Export, portability and final cleanup

**Objective:** Deliver reliable calendar output and a clean project-oriented CLI.

- [ ] **P8-W01:** Implement ordered full-resolution page rendering from project data.
- [ ] **P8-W02:** Implement PDF export using explicit project page order and settings.
- [ ] **P8-W03:** Add export progress, completion state and actionable error messages.
- [ ] **P8-W04:** Implement optional self-contained mode with staged copying and integrity
  checks.
- [ ] **P8-W05:** Implement `.pcd` package export/import, manifest validation, project
  identity handling, schema compatibility and transactional staging.
- [ ] **P8-W06:** Implement Save As / Duplicate Project and reference-only/self-contained
  export modes.
- [ ] **P8-W07:** Replace the legacy CLI with project-oriented commands: `gui`, `scan`,
  `distribute`, `render`, `export` and `doctor`.
- [ ] **P8-W08:** Add end-to-end tests for relinking, embedded assets, package round-trip,
  ordered rendering and PDF order.
- [ ] **P8-W09:** Remove dead old-workflow code, old images, old run configurations and
  obsolete documentation.

**Acceptance criteria**

- Exported pages and PDF follow the exact project page order.
- Reference mode never copies originals.
- Embedded mode is explicit, verified and never destructive.
- Tkinter and `config-cli-gui` are absent from runtime dependencies.
- A project can be reopened after its source folder moves and successfully relinked.

**Phase gate:** Export, persistence and portability are ready for normal use.

## Phase 9: Hardening, documentation and release readiness

**Objective:** Stabilize the new product and make it maintainable.

- [ ] **P9-W01:** Run the complete test suite, lint, formatting, type checks and packaging
  checks; fix regressions introduced by the refactor.
- [ ] **P9-W02:** Perform a manual browser workflow test with the copied Pixabay
  collection.
- [ ] **P9-W03:** Test large source folders, missing files, unreadable images, duplicate
  basenames, unusual aspect ratios and interrupted operations.
- [ ] **P9-W04:** Review UI usability, keyboard accessibility, responsive layout and error
  states.
- [ ] **P9-W05:** Update README, installation, usage, configuration and architecture
  documentation; remove obsolete Tkinter/folder instructions.
- [ ] **P9-W06:** Verify local browser startup and packaging on supported platforms.
- [ ] **P9-W07:** Summarize remaining limitations and prepare a release/merge recommendation.

**Acceptance criteria**

- All automated checks pass, or pre-existing failures are explicitly identified.
- A complete calendar can be created, curated, saved, reopened, relinked and exported.
- The copied Pixabay collection exercises the major editor paths.
- Documentation describes the project-based workflow and its storage behavior.

**Phase gate:** Ready for user acceptance and merge review.

## 6. Cross-phase acceptance criteria

The refactoring is complete when all of the following hold:

1. `uv run photo-composition-designer gui` starts the local web UI at
   `http://127.0.0.1:8767/`.
2. A user can create/open a project, choose a source directory and specify N pages.
3. The app scans the source recursively and previews a distribution without copying or
   moving originals.
4. The user confirms a distribution and receives editable calendar pages.
5. The editor has a side page/collage preview, a main page canvas and a bottom unused
   image panel.
6. The user can add, remove, replace and swap photos using drag-and-drop or keyboard
   alternatives.
7. The unused pool is always derived from persisted assignments.
8. Adding a photo never changes the current layout.
9. Layouts are compact YAML files; users can add their own.
10. GPS behavior is preserved: EXIF first, `locations.ini` fallback, local cached map.
11. A page can be rendered independently from explicit project data.
12. The project survives restart in the central SQLite workspace.
13. Reference mode leaves source files untouched and supports safe relinking.
14. Optional embedded mode makes a project self-contained by copying, never moving.
15. PDF export follows project page order and uses project-specific settings.
16. Tkinter, `config-cli-gui`, `ttkbootstrap` and the old folder CLI are removed.

## 7. Dependencies, risks and unresolved questions

### Main risks

- **Rendering/layout coupling:** The existing collage renderer computes geometry from page
  settings and image count. The YAML/slot adapter must preserve its visual behavior.
- **Legacy folder assumptions:** Existing code derives page order, dates and descriptions
  from folder names. These must be replaced explicitly and tested.
- **Photo identity:** Relative paths alone cannot detect changed files. Metadata and
  optional digests must prevent silent ambiguous relinking.
- **Map caching:** The local shapefile map is expensive. Cache key correctness is critical
  to avoid stale maps after project/source changes.
- **Browser drag-and-drop:** Needs server confirmation, rollback and keyboard alternatives.
- **Source/project location:** A project may live outside the source tree.
- **Performance:** Do not decode all originals per request. Thumbnails and page previews
  must be cached and invalidated by revision.
- **Configuration migration:** Removing `config-cli-gui` is a hard cut. Existing values
  must be catalogued and migrated into typed settings/project defaults.

### Decisions confirmed for this plan

1. Keep Phase 0/1 domain and persistence work as the foundation.
2. Mirror the `image-triage` source structure fully.
3. Web UI first; replace Tkinter and the old CLI workflow.
4. `uv run photo-composition-designer gui` is the primary entry point.
5. Old images are replaced by flat Pixabay images.
6. The editor has three areas: side page/collage thumbnails, main canvas and bottom
   unused-image panel.
7. GPS remains EXIF-first with `locations.ini` fallback and local cached map.
8. Layouts are versioned slot templates; curated existing patterns ship as user-editable
   YAML, and users can add new YAML layouts.
9. Central SQLite workspace and `.pcd` export/import remain the portability model.

## 8. Handoff protocol

- Execute one phase at a time in dependency order.
- At the end of each phase, run the relevant tests/checks, commit completed work packages
  and update the Progress / Handoff block.
- Do not silently change a confirmed product decision. Ask at the phase gate if a phase
  exposes a necessary architecture change.
- Keep commits focused. Do not commit automatically unless requested.
- Do not claim verification unless the commands were actually run.

## Progress / Handoff

- **Mode:** autopilot
- **Plan:** `docs/plans/2026-11-18-web-ui-first-project-workflow.md`
- **Completed:** None. This plan is a planning artifact only; no implementation is done.
- **Active:** None. Awaiting approval to start Phase 0.
- **Next:** Phase 0, starting with P0-W01 image fixture replacement.
- **Relevant files:**
  - `docs/plans/2026-11-18-web-ui-project-workflow.md` (previous plan and Phase 0/1 record)
  - `docs/architecture/web-ui-project-workflow.md`
  - `src/Photo_Composition_Designer/project/`
  - `src/Photo_Composition_Designer/core/`
  - `src/Photo_Composition_Designer/image/`
  - `src/Photo_Composition_Designer/gui/gui.py`
  - `src/Photo_Composition_Designer/cli/cli.py`
  - `tests/test_project_*.py`
  - `tests/test_GeoPlotter.py`, `tests/test_MapRenderer.py`, `tests/test_Photo.py`
  - `/home/paul/PycharmProjects/image-triage/src/image_triage/gui/`
- **Decisions:** Web UI first; full `image-triage`-style source layout; keep Phase 0/1
  domain/persistence; `photo-composition-designer gui` at `127.0.0.1:8767`; replace old
  images with flat Pixabay; three-panel editor; local cached GPS map with existing
  fallback; YAML layouts with user-added files; central workspace and `.pcd` portability.
- **Blockers:** None. No implementation has started.
- **Last verified:** 2026-11-18; repository, existing plan, Phase 0/1 code and
  image-triage reference were inspected. No tests were changed or run.
- **Context status:** clean; ready for user approval and Phase 0 execution.