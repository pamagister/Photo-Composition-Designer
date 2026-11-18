# Web UI and Project-Based Calendar Editor

**Status:** Revised continuation baseline
**Created:** 2026-11-18
**Revised:** 2026-11-18
**Target branch:** `main`
**Repository:** `pamagister/Photo-Composition-Designer`
**Reference implementation:** `pamagister/image-triage`
**Execution mode:** autopilot, with phase-boundary handoffs and explicit user decisions where required
**Predecessor plan (complete):** `docs/plans/2026-11-18-web-ui-first-project-workflow.md`

## 1. Objective and desired outcome

Photo Composition Designer is already a local-first, browser-based calendar editor.
The web UI, project persistence, source inventory, YAML layouts, distribution
proposals, three-panel editor, reference-only export and PDF export are implemented
and covered by tests.

This continuation plan closes the remaining quality and feature gaps instead of
repeating completed work. The goal is a coherent product where:

1. A project renders a complete calendar page from explicit project data,
   including the calendar strip, map, description, anniversaries and photo slots.
2. Every output-affecting value is stored in a per-project output profile, so
   workspace defaults and application updates cannot silently change a project.
3. All page editing actions are available in the browser: assign, remove, replace,
   swap, change layout, crop/focal-point adjustment and edit the page description.
4. Source roots can be safely relinked through the UI when photos move.
5. Distribution proposals can be previewed with per-page samples, regenerated and
   confirmed without leaving partial state.
6. Projects can be duplicated within the workspace, previewed and exported from the
   browser, and managed through a project-oriented CLI.
7. Critical browser flows are covered by both FastAPI TestClient tests and a small
   Playwright suite.

The existing renderer remains the source of truth for final output. The work here
adds composition and integration layers around it; it does not rewrite the renderer.

## 2. Scope, constraints and non-goals

### Mandatory scope

- Full-page rendering from project data: background, photo slots, calendar strip,
  local map, description, anniversaries and title where applicable.
- Typed per-project output profile covering calendar, style, geo, size and layout
  settings, snapshotted at project creation and editable through the UI.
- Page preview rendering at reduced resolution with revision-aware caching.
- Page editing completion: layout change with deterministic slot mapping,
  per-assignment crop/focal-point controls and editable page descriptions.
- Source-root remapping through the browser with match/ambiguity preview.
- Distribution preview with per-page samples, counts, empty slots and overflow.
- Project settings UI, Save As / Duplicate Project within the workspace.
- Web export with progress, warnings and ordered PDF output from the browser.
- Project-oriented CLI commands: `gui`, `scan`, `distribute`, `render`, `export`,
  `duplicate` and `doctor`.
- FastAPI TestClient coverage plus a small Playwright browser suite.
- Documentation and packaging updates for the web UI.

### Explicit constraints

- Original source photos are read-only. Never move, rename, delete or modify them.
- No intermediate per-page/per-week photo folders.
- Adding or removing a photo never changes the current layout.
- The unassigned pool is derived from persisted assignments, not a mutable flag.
- One photo can be assigned at most once per project.
- A slot holds at most one photo; empty slots are valid.
- Keep the application local-first. No cloud storage, accounts or runtime network
  map services.
- Preserve existing calendar, anniversary, location/map, description and smart-crop
  behavior. If a behavior cannot be preserved, document the difference explicitly.
- Keep code and documentation in English. Follow repository `AGENTS.md`, use `uv`,
  `pytest`, `ruff`, 4-space indentation and a 100-character line limit.
- Stage and commit only work-package files and plan updates. Preserve unrelated or
  pre-existing user changes.

### Non-goals

- Multi-user collaboration, accounts, remote hosting or cloud synchronization.
- A general-purpose image-management or photo-rating application.
- Rewriting Pillow/collage rendering without evidence that an adapter is insufficient.
- Manual free-form vector layout authoring. YAML files remain the extension point.
- Legacy folder-calendar import. Existing render behavior is preserved, not the old
  folder workflow.
- Interactive browser maps or third-party map tiles.
- Self-contained `.pcd` packages and embedded assets. These are explicitly deferred
  by user decision; reference-only export remains the supported mode.

## 3. Current implementation baseline

The predecessor plan `docs/plans/2026-11-18-web-ui-first-project-workflow.md` is
complete. Its Phases 0-9 are implemented on `main`.

### 3.1 Already implemented and verified

| Area | Current implementation | Status |
|---|---|---|
| Package layout | `src/photo_composition_designer/{cli,core,db,gui,io,layouts,project,render}` | Done |
| Workspace database | `db/schema.py` schema version 1, WAL, foreign keys, triggers, forward migrations | Done |
| Domain/persistence | `project/models.py`, `project/repositories.py`, `project/services.py` | Done |
| Web foundation | `gui/app.py`, `gui/templating.py`, `gui/settings.py`, Jinja base, static mount, `/health` | Done |
| CLI entry point | Typer app with `gui`, `render` and `export` | Partial |
| Source inventory | `io/scan.py`, `project/inventory.py`, EXIF/GPS, rescan, source-root remap service | Done |
| Media safety | `io/media.py` containment checks, `gui/routes/media.py` thumbnails/originals | Done |
| Layout catalogue | `layouts/loader.py` plus five curated YAML layouts | Done |
| Slot rendering | `render/slot_renderer.py` composites assigned photos into slot rectangles | Partial |
| Distribution | `project/distribution.py` equal/random/date-aware proposals and atomic apply | Done |
| Editing service | `project/editing.py` assign/remove/replace/swap and derived unused pool | Partial |
| Web editor | Three-panel shell, drag-and-drop, keyboard alternatives, HTMX fragments | Done |
| Guided creation | New-project form, layout assignment on create, distribution preview/apply | Done |
| Export | `io/export.py` ordered page rendering and PDF from reference-only photos | Partial |
| Tests | 160 tests pass; `make lint` clean | Done |

### 3.2 Verified baseline commands

```bash
make lint
# All checks passed!

uv run pytest -q
# 160 passed, 1 warning in 8.90s
```

### 3.3 Gaps that this plan must close

1. **Full-page rendering is incomplete.** `render/slot_renderer.py` only pastes
   cropped photos onto a background. It does not render the calendar strip, map,
   description, anniversaries or title. `io/export.py` therefore produces
   photo-only pages and loses established calendar features.
2. **Output profiles are not wired.** `Project.settings` and
   `Project.output_profile` exist as JSON fields, but project creation stores empty
   dictionaries and `ProjectExporter` falls back to global `core.settings.Settings`.
   Existing projects have no typed profile snapshot.
3. **Layout changes are missing from the service and UI.** `PageRepository.set_layout`
   exists, but there is no deterministic mapping service, displaced-photo preview or
   browser workflow.
4. **Crop/focal-point controls are not exposed.** `PhotoAssignment` stores
   `crop_zoom`, `crop_focus_x` and `crop_focus_y`, and the slot renderer accepts
   them, but no route or UI lets the user edit them.
5. **Page descriptions are not editable.** `PageRepository.update_description`
   exists, but there is no route or form.
6. **Page previews and sidebar thumbnails are missing.** The sidebar shows dates
   only; there is no cached page-preview endpoint.
7. **Source-root remapping has no UI.** `InventoryService.preview_remap` and
   `apply_remap` are implemented and tested, but the browser only offers add/scan.
8. **Distribution preview is minimal.** It shows counts but no per-page thumbnails,
   capacity details or explicit overflow/empty-slot presentation.
9. **Project duplication is missing.** Renaming is the only project-level lifecycle
   action; there is no Save As or Duplicate Project.
10. **The CLI is incomplete.** `scan`, `distribute`, `duplicate` and `doctor` are
    not implemented.
11. **No real browser test suite.** Current UI tests use FastAPI TestClient only.
12. **Documentation and packaging need a final pass** for the web UI, output
    profiles and the revised CLI.

## 4. Architecture and decisions

### 4.1 Layering

Keep the established layers and add the missing composition seams:

- **Domain:** project, source root, photo asset, page, layout, slot, assignment and
  distribution proposal models.
- **Application services:** project lifecycle, scanning/relinking, distribution,
  page editing, full-page rendering, preview generation and export.
- **Persistence:** SQLite schema, migrations and repositories. No SQL in routes or
  renderers.
- **Infrastructure:** filesystem access, EXIF/Pillow adapters, local map shapefiles,
  thumbnail/preview caches and PDF writer.
- **Web UI:** FastAPI routes, Jinja templates, HTMX fragments and focused JavaScript.

Route handlers validate input and call services. They must not contain distribution
algorithms, GPS calculations, multi-table SQL or renderer geometry.

### 4.2 Full-page composition

Introduce a composition service that is independent of folders, HTTP and SQLite:

```text
PageRenderInput(
    page_date,
    description,
    layout_snapshot,
    assigned_photos,
    output_profile,
)
```

The service should:

1. Create the page background at the configured page size and DPI.
2. Render assigned photos into slot rectangles with per-assignment crop settings.
3. Render the calendar strip from the page date and profile calendar settings.
4. Render the local map from assigned photo coordinates when enabled.
5. Render the description text when enabled.
6. Preserve anniversaries, holidays, moon phase and title behavior from the existing
   renderers.

`SlotAwareRenderer` remains the slot compositing component. A new
`render/page.py` (or equivalent) owns the page-level composition order and geometry.
The existing `CalendarRenderer`, `MapRenderer`, `DescriptionRenderer`,
`GeoPlotter`, `ObjectDetector` and `SmartCrop` stay in use.

The renderer must not query SQLite or know about FastAPI. The application service
resolves photo references and metadata, constructs the render input and invokes the
renderer.

### 4.3 Output profiles

Define a typed output profile that can be serialized to the existing
`projects.output_profile_json` column. It must cover:

- Calendar: language, holiday countries, start date behavior, orientation,
  short day/month names.
- Style: background color, fonts and colors.
- Geo: map usage, minimal extension, map dimensions.
- Size: page width/height, DPI, JPEG quality, calendar/map heights.
- Layout: margins, spacing, rounded corners, description toggle, PDF toggle,
  object recognition.

Rules:

- New projects snapshot the current defaults into their own profile.
- Existing projects receive a default profile when read, without rewriting their
  rows merely because the application version changed.
- Editing project settings updates the profile and increments the render revision
  of affected pages.
- Workspace defaults may change, but existing project profiles must not change
  silently.
- Export and preview must use the project profile, not the process-global
  `Settings` object.

### 4.4 Page editing and layout changes

- Dragging an unused photo onto an empty slot assigns it.
- Dragging onto an occupied slot requires explicit replace semantics; the replaced
  photo returns to the unused pool.
- Dragging one assigned photo onto another assigned slot swaps assignments.
- Removing a photo clears the slot and returns it to the unused pool.
- Adding or removing a photo never changes the layout.
- Changing a layout uses deterministic slot mapping. Assignments that fit are
  preserved; displaced photos return to the unused pool. The UI previews displaced
  photos before applying the change.
- Crop zoom and focal point are assignment properties, never source mutations.
- Every mutation commits transactionally and increments the page render revision.

### 4.5 Source management

- Store source-root path and POSIX-relative photo paths.
- Resolve photos only as `root / relative_path` with containment validation.
- Preserve relative-path identity when files move via explicit relinking.
- GPS precedence remains EXIF first, `locations.ini` filename fallback second,
  deterministic default map when no coordinates exist.
- Missing coordinates are allowed.
- Never silently bind an ambiguous basename to a different file during relinking.
- Mark missing/unreadable files unavailable without deleting assignments.
- Surface per-photo availability and source-root state in the UI.

### 4.6 Distribution and project creation

`DistributionProposal(pages, unassigned, warnings, strategy, seed)` remains a pure
in-memory proposal.

- The proposal must not mutate project state or the filesystem.
- The UI previews per-page samples, counts, empty slots and overflow.
- Applying a proposal replaces initial assignments in one transaction.
- Random distribution persists its seed and strategy.
- Overflow stays unassigned; empty slots are reported.
- Cancelling or regenerating a proposal leaves no partial assignments.

### 4.7 Portability decision

Reference-only export is the supported portability mode:

- Source-root metadata and relative paths travel with the project.
- Another machine may require source-root relinking.
- Originals are never copied, moved or modified.
- `.pcd` archives and self-contained asset embedding are deferred and must not be
  partially implemented in this plan.

### 4.8 Configuration compatibility

The old `config.yaml`/`config-cli-gui` runtime dependency is gone. The typed
`core.settings.Settings` defaults remain as the source of new-project defaults.
Project output profiles replace runtime coupling. Existing provider dimensions,
DPI/scaling, margins, typography and print settings must be catalogued in the
profile and covered by tests.

### 4.9 Web UI interaction model

Keep the three-area editor:

- Left sidebar: page thumbnails, dates, assigned counts and active-page state.
- Main canvas: rendered page preview with slot/drop affordances and page actions.
- Bottom panel: unused photos with search, sort and counts.

Desktop/laptop is the primary target. Narrow screens may collapse panels into
drawers. Prefer server-confirmed updates; use optimistic UI only when rollback is
reliable. Provide keyboard-accessible alternatives for every drag-and-drop action.

### 4.10 Undo, autosave and concurrency

- Persist every user action immediately in a transaction and show saved/unsaved
  state.
- Add a bounded project edit history or command-based undo/redo only if it can be
  implemented without excessive complexity.
- At minimum, replacement, removal, layout change and crop changes must be atomic
  and recoverable.
- Keep the single-process local deployment assumption. Configure SQLite foreign
  keys, WAL, busy timeout and transaction boundaries. Do not add distributed
  locking or multi-user concurrency machinery.

## 5. Implementation phases and work packages

Work packages are dependency ordered. Each package should be independently
reviewable, testable and committable. Update this plan's Progress / Handoff block at
every phase boundary. Do not combine unrelated phases into one implementation
change.

## Phase 0: Baseline reconciliation and gap lock

**Objective:** Record the actual state of the code and lock the remaining scope.

- [x] **P0-W01:** Reconcile the predecessor plan's completed phases with `main`.
- [x] **P0-W02:** Run `make lint` and `uv run pytest -q`; record the baseline.
- [x] **P0-W03:** Inspect rendering, export, settings, editing, inventory, routes,
  templates, CLI and tests; write the gap list in Section 3.3.
- [x] **P0-W04:** Confirm scope decisions with the user: full feature parity,
  reference-only export, and TestClient plus Playwright coverage.

**Acceptance criteria**

- The plan reflects the current implementation rather than the pre-web baseline.
- Completed work is not re-planned.
- Remaining work has explicit acceptance criteria and dependencies.

**Phase gate:** Do not start Phase 1 until the full-page rendering approach and
output-profile ownership are clear.

## Phase 1: Full-page rendering and output profiles

**Objective:** Make project pages render the complete calendar, not only photos.

- [ ] **P1-W01:** Define a typed `OutputProfile` with calendar, style, geo, size and
  layout sections plus JSON serialization/validation. Provide a factory that
  snapshots `core.settings.Settings` defaults.
- [ ] **P1-W02:** Add a page composition service (`render/page.py` or equivalent)
  that composes background, slot photos, calendar strip, map, description,
  anniversaries and title from a `PageRenderInput`.
- [ ] **P1-W03:** Add `project/rendering.py` to resolve assignments, photos,
  source paths and the project profile, then invoke the composer. The renderer must
  not query SQLite.
- [ ] **P1-W04:** Add reduced-resolution page preview rendering and a cache key that
  includes page render revision, layout version, output-profile hash and render mode.
- [ ] **P1-W05:** Snapshot the output profile on project creation and expose a
  read-time default for existing projects without mutating their rows.
- [ ] **P1-W06:** Add tests for calendar rendering, map rendering, description,
  anniversaries, no-GPS default behavior, profile isolation and preview
  invalidation.

**Acceptance criteria**

- A page rendered from project data contains the calendar strip, map, description
  and photo slots as configured.
- Existing calendar, anniversary, map, description, object-detection and smart-crop
  behavior remains functional or has documented accepted differences.
- Export and preview use the project output profile, not global mutable settings.
- Changing a project profile does not alter another project's output.

**Phase gate:** Full-page output is visually and functionally acceptable before
editing and export work depends on it.

## Phase 2: Page editing completion and previews

**Objective:** Expose every page-level editing action in the browser.

- [ ] **P2-W01:** Implement `PageEditingService.change_layout` with deterministic
  slot mapping, preserved assignments, displaced-photo handling and a preview
  payload.
- [ ] **P2-W02:** Add a layout-change route and UI with displaced-photo confirmation.
- [ ] **P2-W03:** Implement `PageEditingService.set_crop` for zoom and focal point;
  add a route and compact per-slot crop controls.
- [ ] **P2-W04:** Add page-description editing with a route and form; use
  `PageRepository.update_description` and increment the render revision.
- [ ] **P2-W05:** Add a cached page-preview endpoint and render page thumbnails in
  the sidebar.
- [ ] **P2-W06:** Refresh previews and the unused pool after each committed edit;
  show the current render revision and save state.
- [ ] **P2-W07:** Add tests for layout change, crop updates, description editing,
  preview invalidation and rollback on invalid operations.
- [ ] **P2-W08:** Audit the curated YAML layout catalogue against the established
  collage patterns and add missing common arrangements; validate every snapshot.

**Acceptance criteria**

- A user can change a page layout, adjust crops, edit a description and see the
  result without reloading the application.
- Adding or removing a photo never changes the layout.
- Displaced photos are visible before a layout change is confirmed.
- Failed operations leave page and unused-pool state unchanged.

**Phase gate:** All page editing rules are enforceable by services and usable from
the browser.

## Phase 3: Source management UX and reliability

**Objective:** Make source changes safe and understandable in the browser.

- [ ] **P3-W01:** Add a source-root remapping UI that previews matched, ambiguous
  and missing basenames before confirmation.
- [ ] **P3-W02:** Show per-photo availability and missing-source state; allow rescan
  without deleting assignments.
- [ ] **P3-W03:** Improve scan progress/summary reporting for large directories and
  surface the symlink policy.
- [ ] **P3-W04:** Support adding, changing, activating and removing source roots with
  validation and duplicate-basename handling.
- [ ] **P3-W05:** Add tests for remap preview/apply through the UI, missing files,
  source switching and rescan reconciliation.

**Acceptance criteria**

- A moved source root can be relinked through the browser.
- Ambiguous basenames are never silently mapped.
- Missing or unreadable files remain visible and assigned photos are not deleted.
- Source changes are transactional and reported clearly.

**Phase gate:** Source inventory and path resolution are trustworthy before final
export and release work.

## Phase 4: Distribution and project creation UX

**Objective:** Make new-project setup and distribution review complete.

- [ ] **P4-W01:** Extend the distribution preview with per-page thumbnail samples,
  photo counts, empty slots and overflow.
- [ ] **P4-W02:** Allow strategy and seed regeneration without saving until
  confirmation; make confirm idempotent.
- [ ] **P4-W03:** Add a post-creation review screen that opens the editor on the
  first page.
- [ ] **P4-W04:** Add tests for preview, regenerate, cancel and confirm-once
  behavior.

**Acceptance criteria**

- New projects can be created end-to-end without intermediate folders.
- The user sees the distribution before it is applied.
- Cancelling leaves no partial assignments or copied files.
- Initial page count and dates are explicit and persisted.

**Phase gate:** New-project setup is repeatable and understandable.

## Phase 5: Project settings, lifecycle and duplication

**Objective:** Make output settings and project lifecycle first-class.

- [ ] **P5-W01:** Add a project settings UI for calendar language/country, page
  size/DPI, margins, fonts/colors, map options, layout defaults and description/PDF
  toggles.
- [ ] **P5-W02:** Persist settings changes to the project output profile and
  increment affected page render revisions.
- [ ] **P5-W03:** Implement `ProjectService.duplicate_project` as a transactional
  deep copy of pages, layout snapshots, assignments, source roots and profile.
- [ ] **P5-W04:** Add Save As / Duplicate Project UI. Do not implement `.pcd`
  packaging in this plan.
- [ ] **P5-W05:** Add tests for settings persistence, duplicate independence,
  revision invalidation and invalid settings rejection.

**Acceptance criteria**

- Output settings are per-project and survive restart.
- A duplicated project is independent of its source project.
- Reference-only source roots remain relative and relinkable.
- No global settings change can silently mutate an existing project.

**Phase gate:** Project settings and duplication are stable before final export and
release work.

## Phase 6: Web export and preview jobs

**Objective:** Make preview and export usable from the browser.

- [ ] **P6-W01:** Add a web export route with output directory, DPI/quality,
  progress, completion state and actionable warnings.
- [ ] **P6-W02:** Add a full-project preview route that renders pages in explicit
  project order and opens the first page.
- [ ] **P6-W03:** Ensure export uses the project output profile and explicit page
  order for both PNG pages and the combined PDF.
- [ ] **P6-W04:** Add tests for web export, PDF order, profile isolation and missing
  or unreadable assets.

**Acceptance criteria**

- A user can preview and export a project from the browser.
- Exported pages and PDF follow the exact project page order.
- Reference mode never copies originals.
- Export failures produce actionable messages rather than partial silent output.

**Phase gate:** Preview and export are ready for normal use.

## Phase 7: CLI completion and cleanup

**Objective:** Provide a coherent project-oriented CLI.

- [ ] **P7-W01:** Add `scan`, `distribute`, `duplicate` and `doctor` commands;
  keep `gui`, `render` and `export`.
- [ ] **P7-W02:** Implement `doctor` checks for schema version, workspace paths,
  source roots, missing photos, cache directories and output-profile validity.
- [ ] **P7-W03:** Remove dead code and stale documentation references from the old
  folder workflow and `config-cli-gui`.
- [ ] **P7-W04:** Add CLI tests for the new commands and their exit codes.

**Acceptance criteria**

- The CLI covers project scanning, distribution, rendering, export, duplication and
  diagnostics.
- `doctor` reports actionable problems without modifying project data.
- No runtime dependency on Tkinter or `config-cli-gui` remains.

**Phase gate:** The CLI is coherent and documented before release hardening.

## Phase 8: Hardening, accessibility, browser tests and documentation

**Objective:** Stabilize and document the finished workflow.

- [ ] **P8-W01:** Add bounded undo/redo or command history if it can be implemented
  without excessive complexity; otherwise document the limitation.
- [ ] **P8-W02:** Audit keyboard accessibility, focus order, ARIA labels and
  narrow-screen drawer behavior.
- [ ] **P8-W03:** Add a small Playwright CLI suite for add, replace, swap, remove,
  layout change, page navigation and export in Chromium and Firefox; perform a
  manual browser workflow with the copied Pixabay collection.
- [ ] **P8-W04:** Audit thumbnail and preview caching; avoid decoding all originals
  per request.
- [ ] **P8-W05:** Run `make lint`, `make test`, type checking where configured,
  packaging checks and executable workflow verification; fix regressions.
- [ ] **P8-W06:** Update README, usage, configuration and architecture docs for the
  project workflow, output profiles and revised CLI.
- [ ] **P8-W07:** Summarize remaining limitations and prepare a release/merge
  recommendation.

**Acceptance criteria**

- All automated checks pass, or pre-existing failures are explicitly identified.
- Critical browser flows work in Chromium and Firefox.
- Documentation describes the actual workflow and storage behavior.
- Remaining limitations are explicit and acceptable.

**Phase gate:** Ready for user acceptance and merge review.

## 6. Cross-phase acceptance criteria

The continuation is complete when all of the following hold:

1. A page renders the full calendar from explicit project data, including calendar,
   map, description, anniversaries and photo slots.
2. Each project has an independent output profile that controls preview and export.
3. A user can add, remove, replace, swap, change layout, crop and describe pages
   from the browser.
4. The unused pool is always derived from persisted assignments.
5. Adding a photo never changes the current layout.
6. A moved source root can be safely relinked through the browser.
7. Distribution can be previewed with per-page samples, regenerated and confirmed
   exactly once.
8. Projects can be duplicated within the workspace and remain independent.
9. A user can preview and export from the browser, and the PDF follows project page
   order.
10. The CLI provides `gui`, `scan`, `distribute`, `render`, `export`, `duplicate`
    and `doctor`.
11. Reference-only export leaves source files untouched.
12. FastAPI TestClient and Playwright tests cover the critical flows.
13. Documentation matches the implemented workflow.

## 7. Dependencies, risks and unresolved questions

### Main risks

- **Rendering composition order:** Adding calendar, map and description around
  slots may change page geometry. Use the existing renderer geometry and cover it
  with deterministic image assertions.
- **Output-profile migration:** Existing projects have empty profile JSON. Read-time
  defaults must be stable and must not rewrite rows unexpectedly.
- **Map caching:** The local shapefile map is expensive. The cache key must include
  coordinates, geometry, colors, DPI, profile settings and shapefile version.
- **Browser drag-and-drop:** Needs server confirmation, rollback and keyboard
  alternatives.
- **Source/project location:** A project may live outside the source tree. Do not
  assume a fixed relationship between the two.
- **Performance:** Do not decode all originals per request. Thumbnails and page
  previews must be cached and invalidated by revision and profile.
- **Configuration migration:** Removing `config-cli-gui` is a hard cut. Existing
  values must be catalogued and migrated into typed defaults and project profiles.

### Decisions confirmed for this continuation

1. The predecessor web-UI plan is complete; this plan continues from `main`.
2. Full rendering, editing and export parity is in scope, including calendar, map,
   description and anniversaries in rendered output. `.pcd`/self-contained packaging
   is the explicit exception in decision 3.
3. Reference-only export is the supported mode. `.pcd` archives and self-contained
   asset embedding are deferred.
4. Duplicate Project / Save As is implemented as a workspace-level deep copy, not as
   a `.pcd` package.
5. Per-assignment crop/focal-point editing is in scope.
6. Page descriptions are editable and persisted in the project database.
7. Layout changes preserve assignments where possible and preview displaced photos.
8. Output settings are per-project snapshots and are editable through the UI.
9. Testing uses FastAPI TestClient plus a small Playwright suite.
10. Layouts remain versioned YAML templates; manual layout authoring is deferred.
11. No legacy folder-calendar import is required.
12. Tkinter and `config-cli-gui` remain removed from the runtime path.

### Recommended defaults if no contrary decision

- One photo can be assigned to at most one page in a project.
- Each layout has a fixed set of slots; empty slots are valid.
- No automatic reflow when adding/removing photos.
- Layout changes preserve as many assignments as possible and preview displaced
  photos.
- One central workspace SQLite database stores all projects.
- Source references are relative to a remappable source root.
- FastAPI + Jinja2 + HTMX + vanilla JS; no SPA framework.
- Fixed layout templates first; custom layout editor deferred.
- Reference-only export; no `.pcd` packaging in this plan.

## 8. Handoff protocol

- Execute one phase at a time in dependency order.
- At the end of each phase, run the relevant tests and checks, commit the completed
  work packages, and update this plan's Progress / Handoff block.
- Do not silently make a decision listed under "Decisions confirmed" if it
  materially changes the data model or user workflow. Ask the user at the phase gate.
- If a phase exposes a necessary architectural change, update this plan before
  implementing the affected later phases.
- Keep implementation commits focused and stage only work-package files and plan
  updates. Do not commit unrelated or pre-existing user changes.
- Do not claim verification unless commands were actually run.

## Progress / Handoff

- **Mode:** autopilot
- **Plan:** `docs/plans/2026-11-18-web-ui-project-workflow.md`
- **Completed:** Predecessor plan
  `docs/plans/2026-11-18-web-ui-first-project-workflow.md` Phases 0-9 are complete
  and merged to `main`. This continuation Phase 0 is complete: baseline reconciled,
  gap list recorded, scope confirmed and baseline verified.
- **Active:** None. This revision changes only the plan; implementation has not
  started.
- **Next:** Phase 1 (full-page rendering and output profiles). Create one GitHub
  issue for Phase 1 before implementation, then start with P1-W01.
- **Relevant files:**
  - `docs/plans/2026-11-18-web-ui-project-workflow.md`
  - `docs/plans/2026-11-18-web-ui-first-project-workflow.md`
  - `docs/architecture/web-ui-project-workflow.md`
  - `src/photo_composition_designer/render/slot_renderer.py:37-89`
  - `src/photo_composition_designer/render/calendar.py`
  - `src/photo_composition_designer/render/map.py`
  - `src/photo_composition_designer/render/description.py`
  - `src/photo_composition_designer/render/geoplot.py`
  - `src/photo_composition_designer/io/export.py:40-219`
  - `src/photo_composition_designer/io/previews.py`
  - `src/photo_composition_designer/core/settings.py:42-169`
  - `src/photo_composition_designer/project/models.py:13-25,112-123`
  - `src/photo_composition_designer/project/services.py:34-121`
  - `src/photo_composition_designer/project/editing.py:43-174`
  - `src/photo_composition_designer/project/inventory.py:196-278`
  - `src/photo_composition_designer/gui/routes/projects.py:188-280,402-480`
  - `src/photo_composition_designer/gui/routes/editor.py:59-140`
  - `src/photo_composition_designer/gui/templates/partials/editor_canvas.html`
  - `src/photo_composition_designer/cli/app.py:26-56`
  - `tests/test_gui.py`, `tests/test_editor.py`, `tests/test_guided_creation.py`,
    `tests/test_export.py`, `tests/test_inventory.py`
- **Decisions:** Full feature parity; reference-only export only; `.pcd` and
  self-contained assets deferred; workspace-level Duplicate Project; editable output
  profiles; per-assignment crop controls; editable page descriptions; deterministic
  layout changes with displaced-photo preview; TestClient plus Playwright; keep
  workspace SQLite, YAML layouts, one-photo-use and fixed slots; no legacy folder
  import; Tkinter and `config-cli-gui` stay removed.
- **Blockers:** None. No blocking product decisions.
- **Last verified:** 2026-11-18; `make lint` clean; `uv run pytest -q` -> 160 passed.
- **Context status:** Plan revised only. No implementation files changed. Start a
  fresh session for Phase 1 and use this handoff block as the contract.