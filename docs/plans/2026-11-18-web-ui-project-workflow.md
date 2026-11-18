# Web UI and Project-Based Calendar Editor

**Status:** Planning baseline  
**Created:** 2026-11-18  
**Target branch:** `plan/web-ui-calendar-project-workflow`  
**Repository:** `pamagister/Photo-Composition-Designer`  
**Reference implementation:** `pamagister/image-triage`  
**Execution mode:** autopilot, with phase-boundary handoffs and explicit user decisions where required

## 1. Objective and desired outcome

Refactor Photo Composition Designer from a folder-driven desktop workflow into a local-first, project-based calendar editor with a browser UI.

The application must retain and reuse the existing image composition and rendering capabilities wherever practical. The new workflow must separate:

1. **Project and page settings** — calendar format, dates, page count, DPI, margins, calendar settings and output settings.
2. **Image source and inventory** — a selected directory containing the original photos, scanned and referenced in place.
3. **Page composition** — per-page layout selection and ordered assignments of source photos to layout slots.

A new project selects a source directory and a target number of calendar pages. Existing distribution algorithms generate a previewable initial assignment of images to pages without copying or moving images into intermediate folders.

The editor then allows the user to curate each page, replace/remove/add images, change layouts, inspect all pages and see all unassigned images. The project is saved in SQLite. By default, only references to original photos are stored; optional self-contained projects may copy originals into project-managed storage.

The existing renderer remains the source of truth for final page rendering and PDF generation.

## 2. Scope, constraints and non-goals

### Mandatory scope

- Local web UI based on the proven Image Triage stack: FastAPI, Jinja2, HTMX, vanilla JavaScript and CSS.
- Project lifecycle: create, open, save, rename and close projects.
- Directory selection and recursive image discovery, with clear supported-format and error reporting.
- One central workspace SQLite database with versioned schema and migrations; projects are independently exportable as portable `.pcd` archives.
- Image inventory containing stable photo identity, relative path, metadata and availability state.
- Default reference-only storage; optional copy-into-project mode.
- Initial distribution across N calendar pages using the existing distribution strategies, with a preview/confirmation step.
- Independent page layout and photo assignment models.
- Per-page layout selection and image-slot management.
- Drag-and-drop image replacement, removal and addition from the unassigned pool.
- Page thumbnail/navigation sidebar and rendered current-page preview.
- Preview rendering, final page rendering and PDF export.
- Recovery from moved source directories through an explicit source-root remapping workflow.
- Tests, documentation and migration notes.

### Explicit constraints

- Original source photos are read-only. Never move, rename, delete or modify them.
- No intermediate per-page/per-week photo folders in the new project workflow.
- No automatic layout changes when adding an image to a page.
- No automatic reassignment of photos when a user manually edits a page, except for the explicitly defined layout-change rules.
- Preserve existing calendar, anniversary, location/map, description and smart-crop functionality where compatible.
- Keep the application local-first. Do not introduce cloud storage or external image services.
- Keep code and documentation in English, follow repository AGENTS.md, use uv, pytest and Ruff, 4-space indentation and a 100-character line limit.

### Non-goals for this refactoring

- Multi-user collaboration, accounts, remote hosting or cloud synchronization.
- A general-purpose image-management or photo-rating application.
- Replacing Pillow or rewriting the collage algorithms without evidence that this is necessary.
- A full free-form desktop publishing editor with arbitrary vector objects.
- Editing original image pixels or destructive source-file operations.
- Requiring Image Triage as a runtime dependency. Its Pixabay images are a development/demo fixture source, not a runtime dependency.

## 3. Existing implementation findings

The current repository already has useful separation in its rendering stack:

- `CompositionRendererBuilder` constructs the render components.
- `CompositionLayout` calculates page dimensions and available collage area.
- `CompositionPageRenderer` renders a complete page from a list of `Photo` objects, a date and a description.
- `CollageRenderer` performs the collage layout and image placement.
- `CompositionDesignerFactory` wires the rendering dependencies.
- `ImageDistributor` contains equal, random and date-aware distribution algorithms.

The main architectural coupling is above the renderer:

- `CompositionIO.get_photo_folders()` discovers subdirectories.
- `CompositionDesigner.generate_compositions_from_folders()` treats those folders as calendar pages.
- `CompositionDesigner._generate_composition_from_folder()` derives the page index, date and description from folder order.
- `PhotoDistributionWorkflow.distribute()` physically copies photos into generated folders.
- The current Tkinter `MainGui` coordinates configuration, folder distribution, preview and generation.

The refactoring should replace folder-driven page discovery and physical distribution with explicit project/page/photo-assignment data. Do not rewrite the renderer merely to achieve this.

Image Triage provides a proven local GUI pattern: FastAPI application factory, Jinja templates, HTMX partial updates, static CSS/JavaScript, local media endpoints and SQLite repository/migrations. Reuse the pattern, not its photo-library domain model.

## 4. Architecture and decisions

### 4.1 Application layers

Use a small layered architecture:

- **Domain:** project, source root, image asset, calendar page, page layout, slot and assignment models; validation and distribution contracts.
- **Application services:** project creation/opening, source scanning/remapping, distribution preview/apply, page editing, rendering and export.
- **Persistence:** SQLite schema, migrations and repositories. Keep SQL out of route handlers and rendering code.
- **Infrastructure:** filesystem image access, thumbnail/preview cache, Pillow adapters and output files.
- **Web UI:** FastAPI routes, Jinja templates, HTMX fragments and focused JavaScript for drag-and-drop and editor interactions.

Route handlers should validate requests and call application services. They must not contain distribution algorithms or direct multi-table SQL.

### 4.2 Workspace database and portable project packages

Use one central SQLite database for the local workspace. It contains multiple independent projects and is the normal working store.

The workspace owns:

```text
~/.local/share/photo-composition-designer/
  workspace.sqlite3
  thumbnails/
  previews/
  cache/
  exports/
```

Use an XDG-aware/platformdirs data location. Cache and preview files are disposable and rebuildable, not authoritative project data.

A project is a logical aggregate in the workspace database, not a separate database file. It must nevertheless be independently portable through a versioned `.pcd` archive (ZIP container). The archive contains a manifest, a project-only SQLite snapshot or equivalent project-scoped data export, immutable layout snapshots and optional embedded assets. Never include unrelated workspace projects or caches.

Suggested archive structure:

```text
family-calendar-2027.pcd
  manifest.json
  project.sqlite3
  layouts/                 # if layout snapshots are not embedded in DB
  assets/                  # only for self-contained export
  preview/                 # optional cover/overview previews
```

Export from a consistent database snapshot, not by copying the live workspace database. Import validates the manifest/schema version, stages and verifies assets, handles duplicate project IDs explicitly and inserts the project in a controlled transaction.

Provide New Project, Open Project (open an existing workspace project or import a `.pcd` archive), automatic Save, Duplicate Project and Save As/Export. Save As creates an independent project snapshot/archive. Export modes are Reference-only (default) and Self-contained.

Reference-only packages preserve source-root metadata and relative paths; another machine may require source-root relinking. Self-contained packages copy all required originals into `assets/`, rewrite package references and verify integrity. Originals are never moved or modified.

Use SQLite from the Python standard library with explicit repositories and migrations.

### 4.3 Proposed relational model

Use stable integer or UUID primary keys consistently. Suggested logical tables:

- `projects`: project ID, name, calendar year/range, page count, timestamps, settings snapshot, output profile and import metadata.
- `source_roots`: project ID, configured root path, active state, last scan timestamp and source identity.
- `photos`: project ID, stable photo ID, relative path or embedded asset key, filename, file size, mtime, optional digest, dimensions, capture date, GPS metadata and availability.
- `pages`: project ID, page index, date/range, editable description, selected layout snapshot/version, overrides and render revision.
- `layouts` / `layout_slots`: built-in catalogue plus project-owned immutable snapshots with normalized geometry, slot IDs/order and crop defaults.
- `assignments`: project/page/slot/photo IDs, ordering and per-assignment crop/focal-point overrides.
- Optional `project_assets` metadata for embedded photos and integrity hashes.

All project-owned rows are scoped by `project_id`; repositories prevent cross-project assignments. Output-affecting settings and layout snapshots travel with the project package.

Use foreign keys and unique constraints to enforce that a photo is assigned at most once in a project and that a slot has at most one assigned photo. If product requirements later permit reuse, make that a deliberate schema/domain change rather than silently allowing duplicates.

A photo is not owned by a layout. It is an asset assigned to a page slot. Layouts define slots; assignments connect photos to slots.

Avoid persisting redundant `used` flags. The unassigned pool is derived from the photo inventory with a query that excludes all current assignments. This prevents stale pool state after drag-and-drop, removal or undo.

Persist a layout definition/version with the project or retain an immutable layout snapshot per page. A later application update must not silently change the appearance of an existing project.

### 4.4 Image references and portability

Default reference mode (workspace and `.pcd` export):

- Store a canonical source-root path in `source_roots`.
- Store each image path relative to that root, using normalized POSIX-style separators in the database.
- Never rely only on an absolute per-photo path.
- Store file size and modification time; optionally calculate a content digest when scanning or when a robust identity check is needed.
- Resolve a photo as `root / relative_path` and validate that it remains inside the configured root.
- Mark missing/unreadable files unavailable without deleting their project records or assignments.

If files are moved, show a clear source status and offer **Relink source folder**. The user selects a new root; the application validates a sample or all stored relative paths, reports matched/missing/ambiguous files, and only then commits the root change. Never silently bind a project photo to a different file with the same basename. Use relative path plus size/date and, where needed, digest to establish a match.

Optional self-contained mode copies original photos into package `assets/` on explicit export. It must never move originals. Copying is staged/resumable, with integrity checks and clear disk-space reporting. Reference-only export remains the default. Importing a self-contained `.pcd` works without the original source directory.

### 4.5 Image inventory and previews

Scan the chosen source directory recursively, with supported extensions and symlink policy documented. Preserve relative paths and avoid modifying the source.

Create small cached thumbnails for the unassigned pool and page sidebar. Serve source images/previews through controlled media endpoints; do not expose arbitrary filesystem paths through URL parameters. Validate that resolved files are within the selected source root or project asset directory.

The initial demo/test image source is `pamagister/image-triage/images/pixabay` (100 existing photos). Use this collection to exercise mixed subjects, aspect ratios and filenames. Do not fetch images at runtime. Add a small representative, license-compatible fixture subset to this repository only if required for automated tests; document the full Pixabay folder as an optional local demo source.

### 4.6 Distribution workflow

Refactor the existing strategies into a pure distribution service that accepts a photo collection and N pages and returns an in-memory proposal:

`DistributionProposal(pages=[...], unassigned=[...], warnings=[...], strategy=...)`

Initially support the existing strategies:

- Equal distribution.
- Deterministic random distribution.
- Date-aware grouping.

The proposal must not mutate the project or filesystem. The UI displays page counts and representative thumbnails before the user confirms. Applying a proposal replaces the initial assignments in one database transaction.

Handle fewer photos than pages, more photos than page capacity, invalid/missing capture dates and empty pages explicitly. Preserve stable input ordering and make random distribution deterministic through a stored seed.

Do not force the algorithm to fill every page if the layout capacity or input count makes this impossible. Report unassigned images and empty slots.

### 4.7 Layout and page editing

Define layout templates independently of photos. A layout consists of named slots with normalized coordinates (0..1), dimensions, z-order and optional crop mode. Convert normalized geometry to render pixels using the current page dimensions/DPI.

Initial layouts should cover common one-to-four-photo and mixed-size collages. Reuse the existing collage renderer for compatible automatic layouts; introduce a slot-aware renderer adapter rather than duplicating rendering logic.

Page editing rules:

- Dragging an unassigned photo onto an empty slot assigns it.
- Dragging an unassigned photo onto an occupied slot requires an explicit replace action or a clear drop target. The replaced photo returns to the unassigned pool.
- Dragging one assigned photo onto another assigned slot swaps assignments, unless the UI explicitly offers replace semantics.
- Removing an assigned photo clears the slot and returns the photo to the unassigned pool.
- Adding a photo never changes the current layout.
- If there is no free slot, explain that the user must replace an image or choose a layout with more slots.
- Changing a layout preserves assignments where possible, in a deterministic slot-mapping operation. Assignments that do not fit are returned to the unassigned pool. The operation is previewed/confirmed when it would displace photos.
- Per-photo crop/focal point is an assignment property, not a source-photo mutation.

Every edit is committed transactionally and increments the page render revision.

### 4.8 Rendering and export

Introduce a renderer input model that is independent of folder names:

`PageRenderInput(page_date, description, layout_snapshot, assigned_photos, project_settings)`

Adapt `CompositionPageRenderer` and its collaborators to accept this model. Keep compatibility adapters for existing folder-based CLI paths until the new workflow has parity.

The renderer should not query SQLite or know about FastAPI. The application service resolves photo references and metadata, constructs render input and invokes the renderer.

Render previews at reduced resolution and cache them by page revision plus relevant render settings. Final exports use configured DPI/JPEG quality and preserve calendar, anniversary, map, description and smart-crop behavior where applicable.

PDF export must use the explicit page order from the project database, not alphabetical filesystem ordering.

### 4.9 Web UI interaction model

Use FastAPI + Jinja2 + HTMX for page navigation, forms, partial refreshes and status messages. Use vanilla JavaScript for HTML5 drag-and-drop, keyboard-accessible alternative actions, and any client interaction that is awkward in HTMX.

Suggested editor structure:

- **Left sidebar:** all calendar pages with rendered thumbnails, date, assigned-photo count and active-page state.
- **Main canvas:** selected page preview with visible slot/drop targets and page actions.
- **Unassigned-photo strip/panel:** all photos not currently assigned, with thumbnails, search/sort and count.
- **Toolbar:** layout selection, distribution, undo/redo if implemented, save status and export.

The layout should adapt to normal desktop/laptop sizes. On narrow screens, side panels may become collapsible drawers; the desktop editor remains the primary target.

Use optimistic interaction only when rollback is reliable. Prefer server-confirmed updates for assignment/layout changes. Provide visible save/error feedback and prevent duplicate submissions.

### 4.10 Undo, autosave and concurrency

At minimum, persist every user action immediately in a transaction and provide a clear saved/unsaved state. Do not rely on browser-local state as the authoritative project.

Implement a bounded project edit history or command-based undo/redo if the architecture supports it without excessive complexity. At minimum, make replacement, removal and layout change atomic and recoverable.

Use one application process as the initial deployment assumption. Configure SQLite foreign keys, WAL where appropriate, busy timeout and transaction boundaries. Do not add distributed locking or multi-user concurrency machinery.

### 4.11 Configuration compatibility

Keep workspace defaults and project settings distinct. Inspect existing `config.yaml` values and migrate them into workspace defaults/project creation defaults; do not retain runtime coupling to config-cli-gui. Existing photo-provider page dimensions, DPI/scaling, margins, bleed/safe areas, typography and print settings are critical compatibility requirements and must be catalogued and preserved as named output profiles.

Every project snapshots all values affecting final output, including exact provider dimensions/scaling, DPI, margins/bleed, typography, image quality, calendar/anniversary/map settings and rendering options. Later workspace-default changes must not silently mutate existing projects.

Page descriptions are editable in the web editor and persisted as page data. Legacy descriptions-file migration is not required. Anniversary/location inputs belong in project settings; self-contained export must embed required data or clearly report external dependencies.

## 5. Implementation phases and work packages

Work packages are ordered by dependency. Each package should be independently reviewable and committed. Update this plan's Progress / Handoff block at every phase boundary. Do not combine unrelated phases into one large implementation change.

## Phase 0: Repository baseline and design lock

**Objective:** Establish a tested baseline and resolve decisions that would otherwise force schema or UI rework.

- [x] **P0-W01:** Inspect all current rendering, layout, configuration, folder distribution, GUI, CLI and PDF export paths. Map existing tests to those responsibilities.
- [x] **P0-W02:** Inspect Image Triage GUI startup, routing, template structure, media serving, CSS conventions, SQLite migrations and test fixtures. Record which patterns can be reused without copying domain-specific code.
- [x] **P0-W03:** Write concise architecture decision records or an architecture section in project docs for project storage, image identity, layout schema, page capacity, project settings and compatibility.
- [x] **P0-W04:** Establish baseline verification using repository-supported commands; record existing failures separately from regressions.

**Acceptance criteria**

- Existing behavior and important extension points are documented.
- No implementation has begun before schema-affecting decisions are identified.
- A clear list of confirmed decisions and unresolved user decisions exists.

**Phase gate:** Do not start the database implementation until project storage location, page model and legacy compatibility have been decided.

## Phase 1: Domain model and project database

**Objective:** Create the persistent project model without introducing the web UI yet.

- [x] **P1-W01:** Define typed domain models for Project, SourceRoot, PhotoAsset, CalendarPage, LayoutDefinition, LayoutSlot, PhotoAssignment and DistributionProposal.
- [x] **P1-W02:** Implement SQLite connection management, schema creation, schema versioning and forward migrations.
- [x] **P1-W03:** Implement repositories for projects, source roots, photos, pages, layouts and assignments. Keep SQL isolated from domain and web code.
- [x] **P1-W04:** Add foreign keys, unique constraints and transaction-level invariants for unique photo assignment and unique slot occupancy.
- [x] **P1-W05:** Add project create/open/close/save services and project settings snapshots.
- [x] **P1-W06:** Add tests for database initialization, migration, constraints, rollback, reopen and persistence.

**Acceptance criteria**

- A project can be created, closed and reopened with identical settings and page state.
- Database constraints prevent duplicate assignments and duplicate slot occupancy.
- A project can contain empty pages and unassigned photos.
- The schema is versioned and migration tests are repeatable.

**Phase gate:** Domain and persistence APIs are stable before filesystem scanning or GUI work.

## Phase 2: Source scanning, references and portability

**Objective:** Make a directory of original photos a first-class project source without copying or restructuring it.

- [ ] **P2-W01:** Implement recursive image discovery with an explicit extension list, deterministic ordering and symlink policy.
- [ ] **P2-W02:** Implement metadata extraction using the existing Photo/EXIF behavior where possible; avoid reopening each image repeatedly.
- [ ] **P2-W03:** Persist source-relative paths, metadata, file size, mtime and availability. Add optional content digest support.
- [ ] **P2-W04:** Implement safe source resolution and media access boundaries; prevent path traversal and access outside configured roots.
- [ ] **P2-W05:** Implement rescan/reconcile behavior: add new files, detect changed files and mark missing files without deleting project history.
- [ ] **P2-W06:** Implement source-root remapping with preview, match counts, ambiguity handling and atomic confirmation.
- [ ] **P2-W07:** Add thumbnail cache generation and tests for unreadable files, missing roots, moved roots, duplicate basenames and traversal attempts.

**Acceptance criteria**

- Scanning a source directory creates inventory records without copying, renaming or moving source images.
- A project stores paths relative to its source root.
- Missing references remain visible and can be relinked safely.
- A source-root change cannot silently map a record to an ambiguous file.

**Phase gate:** Source inventory and path resolution are stable before distribution and media UI work.

## Phase 3: Distribution proposals without intermediate folders

**Objective:** Reuse the existing distribution algorithms as pure project services.

- [ ] **P3-W01:** Extract equal, deterministic-random and date-aware distribution into a service that returns a proposal rather than writing folders.
- [ ] **P3-W02:** Define explicit behavior for N pages, empty pages, insufficient images, overflow, unknown dates and capacity limits.
- [ ] **P3-W03:** Persist random seed and strategy metadata so proposals can be reproduced.
- [ ] **P3-W04:** Implement proposal summaries and preview data, including per-page image samples and unassigned counts.
- [ ] **P3-W05:** Implement atomic apply/replace of the initial proposal in the project database.
- [ ] **P3-W06:** Add deterministic unit and integration tests against the existing algorithms and representative Pixabay samples.

**Acceptance criteria**

- Distribution never creates intermediate folders and never copies source images.
- Previewing a proposal does not modify project state.
- Applying a proposal updates all page assignments atomically.
- The same input, strategy and seed produce the same proposal.
- Overflow and underfilled pages are reported, not silently discarded.

**Phase gate:** Distribution output is a stable list of page-to-photo assignments, independent of rendering and UI.

## Phase 4: Layout catalogue and slot-based rendering

**Objective:** Decouple layout definitions and photo assignments while preserving the existing visual rendering quality.

- [ ] **P4-W01:** Define a versioned layout definition format with normalized slot geometry, order, z-index and crop defaults.
- [ ] **P4-W02:** Create initial layouts covering one to four photos and mixed large/small compositions.
- [ ] **P4-W03:** Implement layout validation: bounds, overlap policy, minimum dimensions and unique slot IDs.
- [ ] **P4-W04:** Introduce a renderer adapter that maps slot-based page data to existing collage/page rendering components.
- [ ] **P4-W05:** Adapt the page renderer to accept explicit page date, description, layout snapshot and photo assignments instead of deriving these from folder names.
- [ ] **P4-W06:** Preserve calendar, anniversary, map, description, object detection and smart-crop behavior through regression tests.
- [ ] **P4-W07:** Add visual regression fixtures or deterministic render assertions for representative page layouts.

**Acceptance criteria**

- A page can be rendered from explicit page data without creating or reading a page folder.
- Layout definitions contain no photo identities.
- Photo assignments contain no geometry duplicated from the layout.
- Existing rendering features remain functional unless a documented incompatibility is accepted.
- Layout version changes do not silently alter saved project pages.

**Phase gate:** Rendering from project data is visually and functionally equivalent for supported existing features.

## Phase 5: Page editing services and assignment invariants

**Objective:** Implement the complete editing behavior independently of HTTP and browser code.

- [ ] **P5-W01:** Implement add-to-empty-slot, remove, replace and swap assignment operations.
- [ ] **P5-W02:** Derive the unassigned pool from inventory and current assignments; expose efficient repository queries.
- [ ] **P5-W03:** Implement layout change with deterministic slot mapping and displaced-photo handling.
- [ ] **P5-W04:** Add preview/confirmation for layout changes that displace assigned photos.
- [ ] **P5-W05:** Implement per-assignment crop/focal-point overrides without modifying original files.
- [ ] **P5-W06:** Increment page render revisions and invalidate only affected previews after edits.
- [ ] **P5-W07:** Add transactional tests for swaps, replacements, removals, duplicate assignment rejection, layout changes and rollback.

**Acceptance criteria**

- Every photo is either assigned once or appears in the unassigned pool.
- Adding a photo never changes a page layout.
- Full pages reject additions unless the user replaces a photo or changes layout.
- Replaced/removed/displaced photos return to the unassigned pool.
- Failed operations leave both page and pool state unchanged.

**Phase gate:** All editing rules are enforceable by application services, not merely by UI conventions.

## Phase 6: Web application foundation and project lifecycle

**Objective:** Replace the Tkinter interaction surface with a local web application using Image Triage conventions.

- [ ] **P6-W01:** Add FastAPI application factory, startup/shutdown lifecycle, static files, Jinja templates and health endpoint.
- [ ] **P6-W02:** Add project selection/open/create workflow and project status display.
- [ ] **P6-W03:** Add source directory selection through a safe local-only directory chooser or a clearly constrained path-entry workflow appropriate to the supported platforms.
- [ ] **P6-W04:** Add scan progress, scan result summary, missing-source state and error reporting.
- [ ] **P6-W05:** Add server-side page routes and HTMX partials for project, inventory and page navigation.
- [ ] **P6-W06:** Add controlled thumbnail/media endpoints with cache headers and correct content types.
- [ ] **P6-W07:** Add API/UI integration tests using FastAPI TestClient and temporary project/source directories.
- [ ] **P6-W08:** Add the local web-app entry point and packaging dependencies; remove the Tkinter GUI and its GUI-specific dependencies.

**Acceptance criteria**

- The application starts locally and opens a project in a browser.
- A user can create/open a project and scan a source directory.
- The server never serves arbitrary filesystem paths.
- UI operations use application services and do not embed business logic in route handlers.

**Phase gate:** Project creation and source inventory are usable through the browser before building the full editor.

## Phase 7: Calendar editor UI and drag-and-drop

**Objective:** Deliver the central editing experience.

- [ ] **P7-W01:** Build the three-area editor shell: page thumbnails, current-page canvas and unassigned-photo panel.
- [ ] **P7-W02:** Render the current page with visible slot boundaries and assignment affordances.
- [ ] **P7-W03:** Implement accessible drag-and-drop from unassigned photos to empty/occupied slots.
- [ ] **P7-W04:** Implement drag-and-drop swap/replace behavior for photos already assigned to the current page.
- [ ] **P7-W05:** Add explicit remove actions and ensure removed photos immediately reappear in the unassigned pool.
- [ ] **P7-W06:** Add layout selection and confirmation UI; show displaced photos before applying a layout change.
- [ ] **P7-W07:** Add search, sort and pagination/virtualization for the unassigned photo inventory.
- [ ] **P7-W08:** Add page selection, previous/next navigation, status indicators and responsive side-panel behavior.
- [ ] **P7-W09:** Add keyboard-accessible alternatives for all drag-and-drop actions.
- [ ] **P7-W10:** Add browser-level tests for add, replace, swap, remove, layout change and page navigation.

**Acceptance criteria**

- All requested editing actions work without reloading the whole application.
- The unassigned pool always reflects persisted assignments.
- The current layout remains unchanged when adding or removing a photo.
- Page thumbnails and current-page preview reflect committed changes.
- Core editing remains possible without a mouse.

**Phase gate:** The user can complete a full calendar's image curation from the browser.

## Phase 8: Distribution wizard, preview and project setup

**Objective:** Make new-project creation a guided, safe workflow.

- [ ] **P8-W01:** Build the new-project wizard for project location/name, calendar settings, page count and source directory.
- [ ] **P8-W02:** Add distribution strategy selection and preview before committing assignments.
- [ ] **P8-W03:** Show per-page thumbnail samples, photo counts, empty slots and unassigned overflow.
- [ ] **P8-W04:** Allow the user to change strategy/seed and regenerate a proposal without changing the saved project until confirmation.
- [ ] **P8-W05:** Add a post-creation review screen that opens the editor on the first page.
- [ ] **P8-W06:** Add tests for cancelling/revising proposals and confirming a proposal exactly once.

**Acceptance criteria**

- New projects can be created end-to-end without an intermediate folder step.
- The user sees the distribution before it is applied.
- Cancelling the wizard or proposal does not leave partial assignments or copied files.
- The initial page count and dates are explicit and persisted.

**Phase gate:** New-project workflow is end-to-end and repeatable.

## Phase 9: Export, legacy compatibility and project portability

**Objective:** Deliver reliable calendar output and avoid breaking established workflows.

- [ ] **P9-W01:** Implement ordered full-resolution page rendering from the project database.
- [ ] **P9-W02:** Implement PDF export using explicit project page order and project settings.
- [ ] **P9-W03:** Add export progress, completion state and actionable error messages.
- [ ] **P9-W04:** Implement optional self-contained mode by copying originals into project assets with integrity checks and resumable behavior.
- [ ] **P9-W05:** Add project backup/restore guidance and validate project portability between machines.
- [ ] **P9-W06:** Implement `.pcd` package export/import, manifest validation, project identity handling, schema compatibility and transactional staging.
- [ ] **P9-W07:** Implement Save As / Duplicate Project and Reference-only / Self-contained export modes.
- [ ] **P9-W08:** Replace the legacy CLI with focused workspace/project commands for source scan, distribution, render, export and local web-server startup. Remove config-cli-gui and obsolete Tkinter dependencies.
- [ ] **P9-W09:** Add end-to-end tests for source relinking, embedded assets, package round-trip, rendering and PDF order.

**Acceptance criteria**

- Exported pages and PDF follow the exact project page order.
- Reference mode never copies originals.
- Embedded mode is explicit, verified and never destructive to source files.
- The new CLI operates on workspace projects and offers documented project, scan, distribution, render and export commands. Tkinter and config-cli-gui are no longer runtime dependencies.
- A project can be reopened after its source folder is moved and successfully relinked.

**Phase gate:** Export, persistence and portability are ready for normal use.

## Phase 10: Hardening, documentation and release

**Objective:** Stabilize the new workflow and make it maintainable.

- [ ] **P10-W01:** Run the complete test suite, lint, formatting, type checks and relevant packaging checks. Fix regressions introduced by the refactoring.
- [ ] **P10-W02:** Perform a manual browser workflow test using the 100-photo Pixabay collection from Image Triage.
- [ ] **P10-W03:** Test large source folders, missing files, unreadable images, duplicate basenames, unusual aspect ratios and interrupted operations.
- [ ] **P10-W04:** Review UI usability, keyboard accessibility, responsive layout and error states.
- [ ] **P10-W05:** Update README, installation, usage, configuration and architecture documentation; remove obsolete Tkinter/folder workflow instructions where appropriate.
- [ ] **P10-W06:** Update packaging and executable workflows for the web UI; verify local browser startup on supported platforms.
- [ ] **P10-W07:** Summarize remaining limitations and prepare a release/merge recommendation.

**Acceptance criteria**

- All automated checks pass, or pre-existing failures are explicitly identified.
- A complete calendar can be created, curated, saved, reopened, relinked and exported.
- The demo collection exercises the major editor paths.
- Documentation describes the new project-based workflow and its storage behavior.

**Phase gate:** Ready for user acceptance and merge review.

## 6. Acceptance criteria across the complete mission

The refactoring is complete when all of the following hold:

1. A user can create a project, choose a photo source directory and specify N calendar pages.
2. The application scans the source and previews a distribution using existing strategies.
3. The user confirms the distribution and receives editable calendar pages without intermediate image folders.
4. Each page has an independent, persisted layout and a set of slot assignments.
5. The user can add, remove, replace and swap photos using drag-and-drop or accessible alternatives.
6. The unassigned-photo pool is always correct and is derived from persisted assignments.
7. Adding a photo never changes the current layout.
8. All pages appear in a thumbnail navigation sidebar.
9. A page can be rendered independently from its explicit project data.
10. The project survives application restart and is stored in SQLite.
11. Reference mode leaves source files untouched and supports source-root relinking.
12. Optional embedded mode makes a project self-contained by copying, never moving, originals.
13. PDF export follows the project page order and uses project-specific settings.
14. Existing rendering features and CLI behavior are preserved or migrated with explicit documentation.

## 7. Dependencies, risks and unresolved questions

### Main risks

- **Rendering/layout coupling:** Current collage rendering calculates geometry dynamically from page settings and image count. Slot-based layouts may require an adapter and incremental renderer refactoring. Avoid replacing the renderer wholesale.
- **Legacy folder assumptions:** Several existing paths derive page order, date and descriptions from folder order. Compatibility must be explicit and tested.
- **Photo identity:** Relative paths alone cannot detect replacement files. Use metadata and optional digest checks; never silently relink ambiguous matches.
- **Layout migration/versioning:** Existing saved pages must remain visually stable when default layouts evolve.
- **Browser drag-and-drop:** Must support explicit server confirmation, rollback on failure and keyboard alternatives.
- **Project/source location:** A project may live outside the source tree. Do not assume a fixed relationship between the two.
- **Performance:** Generate thumbnails once and cache page previews by revision; avoid repeatedly decoding all original images on every UI request.

### Decisions to confirm before implementation

1. **Workspace database:** Confirmed: one central SQLite workspace database containing multiple projects.
2. **Portable project format:** Confirmed direction: `.pcd` ZIP archive with manifest, project-only data snapshot, layout snapshots and optional embedded assets. Provide Open/Import, Save As/Export and Duplicate Project.
3. **Legacy calendars:** No import of existing folder-based calendars is required. Preserve existing provider dimensions, scaling, print settings and established layout catalogue/style.
4. **Page capacity:** Confirmed: fixed slot count per layout; empty slots are valid and overflow remains unassigned.
5. **Photo reuse:** Confirmed: one use per project. To repeat a title photo, the user can place a separate copy in the watched source directory; these are distinct assets.
6. **Self-contained mode:** Reference-only is the default; self-contained `.pcd` export embeds copies of all required images.
7. **Descriptions:** Confirmed: page descriptions are editable and persisted directly in the editor. No legacy descriptions-file migration is required.
8. **Layout freedom:** Confirmed: fixed templates initially, with a broad catalogue at least as extensive as the existing layouts. Manual layout authoring is deferred.
9. **Crop editing:** Confirmed: per-assignment crop controls (zoom and focal-point/pan adjustment), without modifying source photos.
10. **Runtime/deployment:** Confirmed: local-only web application. Remove Tkinter; replace the CLI with a cleaner project-oriented CLI. Remove config-cli-gui.
11. **Directory selection:** Deferred to Phase 6. Phase 0-2 introduce no web UI and accept a validated absolute source path in the service layer.

### Recommended defaults if no contrary decision

- One photo can be assigned to at most one page in a project.
- Each layout has a fixed set of slots; empty slots are valid.
- No automatic reflow when adding/removing photos.
- Layout changes preserve as many assignments as possible and preview any displaced photos.
- One central workspace SQLite database stores all projects.
- `.pcd` is the portable project package; Save As/Export and Open/Import provide portability.
- Source references are relative to a remappable source root; self-contained export embeds required assets.
- Output settings and immutable layout snapshots travel with `.pcd` packages.
- FastAPI + Jinja2 + HTMX + vanilla JS; no SPA framework.
- One workspace SQLite database using the standard library with explicit migrations and repositories.
- Fixed layout templates first; custom layout editor deferred.
- No legacy calendar import; preserve provider sizing/scaling and existing layout catalogue.
- Remove Tkinter and config-cli-gui; replace CLI with project-oriented commands.

## 8. Handoff protocol

- Execute one phase at a time in dependency order.
- At the end of each phase, run the relevant tests and checks, commit the completed work packages, and update this plan's Progress / Handoff block.
- Do not silently make a decision listed under "Decisions to confirm" if it materially changes the data model or user workflow. Ask the user at the phase gate.
- If a phase exposes a necessary architectural change, update this plan before implementing the affected later phases.
- Keep implementation commits focused; do not commit automatically unless the user explicitly requests it.
- Do not claim verification unless commands were actually run.

## Progress / Handoff

- **Mode:** autopilot
- **Plan:** `docs/plans/2026-11-18-web-ui-project-workflow.md`
- **Completed:** Phase 0 and Phase 1 complete. Phase 0 architecture baseline in `docs/architecture/web-ui-project-workflow.md` (`0c1408d`). Phase 1 project package with domain models, SQLite schema/migrations, repositories, constraints and lifecycle services; 23 new tests; full suite 129 passed.
- **Active:** None. Phase 1 is complete and committed.
- **Next:** Phase 2 (issue #14): recursive image discovery, metadata extraction, source-relative persistence, safe path resolution, rescan/reconcile, source-root remapping and thumbnail cache. Directory-picker work stays deferred to Phase 6.
- **Relevant files:**
  - `docs/architecture/web-ui-project-workflow.md`
  - `docs/plans/2026-11-18-web-ui-project-workflow.md`
  - `.github/workflows/main.yml`
  - `src/Photo_Composition_Designer/project/models.py`
  - `src/Photo_Composition_Designer/project/db.py`
  - `src/Photo_Composition_Designer/project/repositories.py`
  - `src/Photo_Composition_Designer/project/services.py`
  - `tests/test_project_db.py`
  - `tests/test_project_repositories.py`
  - `tests/test_project_services.py`
  - `src/Photo_Composition_Designer/common/Photo.py`
  - `src/Photo_Composition_Designer/core/base.py`
  - `src/Photo_Composition_Designer/core/composition_io.py`
  - `src/Photo_Composition_Designer/tools/ImageDistributor.py`
- **Decisions:** One workspace SQLite database; portable `.pcd` archives; reference-only default and self-contained export; no legacy calendar import; preserve provider sizing/scaling and existing layout catalogue; fixed slots; one photo use per project; editable page descriptions; per-assignment crop controls; local FastAPI/Jinja/HTMX UI; remove Tkinter/config-cli-gui; project-oriented CLI; source-directory picker deferred to Phase 6.
- **Blockers:** None. No blocking product decisions.
- **Last verified:** 2026-11-18; `make test` green (129 passed) after Phase 1 implementation.
- **Context status:** clean; continue with Phase 2 in this session.
