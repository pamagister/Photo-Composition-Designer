# Automatic Collage Layout: Dynamic, Content-Aware Grids

**Status:** Ready for execution
**Created:** 2026-11-21
**Target branch:** `main`
**Repository:** `pamagister/Photo-Composition-Designer`
**Execution mode:** autopilot, with phase-boundary handoffs and one GitHub issue per phase
**Predecessor work:** Layout catalogue and slot renderer (`src/photo_composition_designer/layouts/`),
dropzone editing workflow (`docs/plans/2026-11-19-collage-image-workflow.md`)

## 1. Objective and desired outcome

Collages currently require a fixed YAML layout template whose slot count is known before
any photo is chosen. This plan adds an **automatic layout** that derives the grid from the
photos themselves, so a page can hold 1 to 30 (or more) photos without the user picking a
template or a slot count.

Desired outcomes:

1. **Auto layout at the top of every layout list** (new project and per-page layout change).
2. **Content-aware geometry.** The algorithm uses each photo's aspect ratio (and optionally
   its YOLO importance) to produce a balanced, full-bleed tiling of the collage content box.
3. **Correct special cases**: one photo fills the page; two photos split along the better
   axis for the canvas orientation; one portrait plus two landscapes on a landscape canvas
   places the portrait on one side and stacks the two landscapes next to it.
4. **Ergonomic photo management**: a generic drop zone in the layout panel, removal that
   leaves the grid untouched, explicit reflow, and automatic growth when no empty slot
   remains.
5. **No schema migration and no regression** for static layouts, cropping, replacement,
   swapping, distribution, export and preview caching.

## 2. Scope, constraints and non-goals

### Mandatory scope

- A pure, deterministic layout engine that turns an ordered photo list and a canvas aspect
  ratio into normalized slot rectangles.
- An `auto` entry at the top of the layout catalogue used by the project wizard and the
  per-page layout selector.
- Persisted auto layout snapshots that are regenerated when the photo set or the canvas
  geometry changes.
- Photo management on auto pages: add (fill empty slot, otherwise re-flow), remove (keep the
  hole), reflow, remove empty slots.
- Optional YOLO-based importance weighting controlled by the existing
  `layout.image_score_factor`, with a graceful fallback to `1.0`.
- Distribution support through a configurable target slot count for auto pages.
- Tests at unit, service, route and (where useful) browser level.

### Explicit constraints

- The layout engine must be pure: no file, database or network access, no randomness.
- The existing rendering path (`SlotAwareRenderer`, `SmartCrop`, `PageComposer`) stays
  unchanged; auto layouts are persisted as ordinary layout snapshots.
- All mutations remain server-confirmed and transactional.
- No new database tables; no schema version bump.
- Every new pointer interaction keeps the keyboard-accessible controls in the right-hand
  panel.

### Non-goals

- A fully free-form canvas editor (free dragging, resizing, arbitrary rotation).
- Per-photo manual slot geometry overrides.
- Changing the static YAML layouts or the layout catalogue format.
- New crop modes or a new renderer.
- Automatic photo selection by content (the algorithm arranges the photos it is given).

## 3. Architecture and decisions

### 3.1 Prototype result (P0, complete)

A standalone prototype was used to validate the algorithm before integration. It lives
outside the repository and is not shipped:

`/home/paul/.opencode/plan/auto_layout_proto.py`

Generated review artefacts (untracked, safe to delete):

- `collages/auto_01.jpg` … `collages/auto_30.jpg` for 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15,
  20, 25 and 30 photos, all 1920×1080 (FULL HD).
- `collages/auto_contact_sheet.jpg` — overview of all counts.
- `collages/auto_importance_off_06.jpg` / `auto_importance_on_06.jpg` — importance-weighting
  comparison.

Verified properties:

| Check | Result |
| --- | --- |
| Coverage for n = 1…30 | `1.000000` |
| Overlap for n = 1…30 | `0.0` |
| 1 photo | fills the whole canvas |
| 2 landscapes, landscape canvas | side by side |
| 2 landscapes, portrait canvas | stacked |
| 2 portraits, landscape canvas | side by side |
| 1 portrait + 2 landscapes, landscape canvas | portrait left (47 %), two landscapes stacked right (53 %) |
| 3 landscapes, landscape canvas | two stacked left, one right |
| Search time | 8 ms (n=6), 44 ms (n=10), 188 ms (n=20), 381 ms (n=30) |

### 3.2 Algorithm

The engine sorts the photos by orientation (portrait, square, landscape) and preserves the
input order inside an orientation class. It then runs a memoised, greedy top-down split
with a one-level lookahead over contiguous slices of that sequence.

Candidate structures for a box with aspect `A`:

1. **Row** — all photos side by side, widths proportional to `aspect × importance`.
2. **Column** — all photos stacked, heights proportional to `importance / aspect`.
3. **Binary split** along x (side by side) or y (stacked), with four allocations of the
   first group's share: aspect-derived row, aspect-derived column, equal, and
   importance-proportional ("fair share").

The cost of a candidate is the area-weighted mean absolute log-ratio between each photo's
resulting cell aspect and the photo's own aspect (the real cropping distortion), plus a
one-sided **fairness penalty** that punishes any group receiving less area than its
importance-weighted share. The one-sided form is deliberate: giving a small group more room
than its fair share is acceptable, while starving a large group produces slivers. Without
this term the search happily produced a 2.5 %-wide column of slivers next to one huge photo.

The search is deterministic: no random seeds, no time-based decisions. The same photo set
and canvas aspect always produce the same tiling.

### 3.3 Why a persisted snapshot instead of a render-time layout

The data model is "immutable layout snapshot plus assignments by slot id". Rendering,
editor overlays, distribution, export and preview-cache keys all depend on that snapshot.
Auto geometry depends on the photo set and the canvas aspect, so the snapshot must be
regenerated whenever those change.

Chosen design:

- Auto snapshots use `key="auto"` and a strictly increasing `version` (`max(version) + 1`
  for that key inside the same transaction), so every page owns its own snapshot.
- Slots are named `auto_0 … auto_{n-1}` in reading order.
- Regeneration remaps assignments by slot index, preserving each assignment's
  `crop_zoom`, `crop_focus_x` and `crop_focus_y`.
- `PageRepository.set_layout` increments `render_revision`, so the existing preview cache
  key (`layout_id`, `layout_version`, `render_revision`) invalidates automatically.
- A page with zero photos receives a snapshot with zero slots; the renderer produces an
  empty collage and the editor shows a single drop zone.

Rejected alternatives:

- **Fully dynamic layout without slot ids** (nullable `slot_id` plus a position column).
  This would require a schema migration and changes to every consumer of `assignments`
  (renderer, editor, distribution, export, tests).
- **Compute only at render time.** The editor needs stable slot ids for assignments, crop
  overrides, dropzones and swap operations.

### 3.4 Code reuse

From `temp/PhotoCollage.py`:

- The idea of aspect-driven recursive nesting.
- `linear_partition` / `linear_partition_table` as an optional building block for
  row-balanced partitions; not required by the chosen algorithm.
- **Not reused:** `create_batches` and the random target aspects (non-deterministic),
  "resize rows to minimum width" composition (does not fill a fixed canvas), the CLI, and
  corner rounding (already provided by the project renderer).

From the 1.0.7 `CollageRenderer`:

- The `SplitNode` / `ImageNode` plus weights model.
- `_chooseBestThreeLayout` as the explicit 3-photo expectation (now subsumed by the cost
  search and used as a test fixture).
- `_calculateLayoutWeight` (aspect) and `_calculateImageImportance` (YOLO score) as the
  importance formula.
- **Not reused:** the `_renderLayout` bug `ch = (x + width) - current_y` (must be
  `y + height`), and the `PATTERNS` row-ordering heuristics (optional).

Image analysis: **yes**. The project already provides `render/object_detector.py`
(YOLO26n ONNX with a disk cache and preview-worker warm-up), `render/smart_crop.py`
(detection-weighted crop anchor) and the currently unused `layout.image_score_factor`.
The auto layout uses detections only for the area-weighting factor; cropping itself keeps
using the existing `SmartCrop` path.

### 3.5 Confirmed product decisions

| Topic | Decision |
| --- | --- |
| Removing a photo | The slot remains empty; the grid is not re-rastered. A separate "Reflow" action restores n slots. |
| Adding a photo | Fill an empty slot if one exists; otherwise regenerate with n+1 photos. |
| Image analysis | YOLO importance on by default, with a fallback to `1.0` when the model or detections are unavailable. |
| Photo order | The algorithm may group by orientation; the input order is kept inside an orientation class. |
| Distribution | Auto pages receive a configurable target slot count (default 6); the layout is generated after distribution. |

### 3.6 Worked example

Three photos (one portrait, two landscapes) on a 1920×1080 canvas produce:

```text
+---------------------------+-------------+
|                           |  landscape  |
|         portrait          +-------------+
|                           |  landscape  |
+---------------------------+-------------+
```

This matches the requested "portrait on one side, the two landscapes stacked next to it".

## 4. Phases and work packages

### Phase 1: Pure layout engine

**Status:** Done (pushed, CI green 2026-11-21)

**Objective:** Add a deterministic, side-effect-free layout engine and prove its geometry.

- [x] P1-W01: Add `src/photo_composition_designer/layouts/auto_layout.py` with
  `AutoPhoto` (photo id, width, height, importance), `AutoSlot` (key, x, y, width, height)
  and `build_auto_layout(photos, canvas_aspect, *, importance_weight=1.0, balance_weight=0.2)`.
  Port the prototype algorithm, replace all randomness with deterministic ordering, and
  document the cost model.
- [x] P1-W02: Add `tests/test_auto_layout.py` covering: one photo fills the canvas; two
  photos choose the axis by canvas and photo orientation; portrait + two landscapes on a
  landscape canvas; exact tiling (coverage `1.0`, no overlap) for n = 1…30; determinism
  (same input twice yields identical slots); importance weighting changes the allocation;
  empty input returns an empty tuple.
- [x] P1-W03: Add a performance test that builds a 30-photo layout in under an agreed
  budget (target ≤ 1 s; current prototype is ~0.4 s).

**Acceptance criteria**

- `build_auto_layout` performs no I/O and is importable without FastAPI, SQLite or Pillow.
- All geometry tests pass for canvas aspects 0.5, 1.0, 1.5, 1.78 and 2.4.
- `make lint` and the new tests are green.

**Phase gate:** The engine is stable before any application wiring.

### Phase 2: Catalogue integration and layout selection

**Status:** Done (pushed, CI green 2026-11-21)

**Objective:** Make "Automatic" selectable at the top of every layout list and persist it.

- [x] P2-W01: Add a `layout_choices()` helper that returns the auto entry first, followed
  by the YAML catalogue. Use it in `new_project.html`, `partials/editor_canvas.html` and the
  read-only `layouts.html`. Keep `load_catalogue()` unchanged for existing callers.
- [x] P2-W02: Extend `PageEditingService` with auto support: `_resolve_template("auto")`
  returns a virtual descriptor, `_ensure_auto_layout(connection, photos, canvas_aspect)`
  creates a new snapshot with a fresh version, and `plan_layout_change` /
  `change_layout` handle the auto key. Remap assignments by slot index.
- [x] P2-W03: Handle auto in `_assign_layout_to_all_pages` and in project creation so a new
  project with the auto default gets empty auto snapshots on every page.
- [x] P2-W04: Add service tests for switching to auto with 0, 3 and 7 assigned photos and
  for the preserved crop overrides; add `TestClient` tests for the layout preview and apply
  endpoints with `layout_key=auto`.

**Acceptance criteria**

- "Automatic" is the first option in the project wizard and the per-page layout selector.
- Switching to auto creates a full-bleed tiling for the currently assigned photos.
- Existing static layouts still resolve and render unchanged.
- Preview cache keys change after an auto layout switch.

**Phase gate:** Auto can be selected and rendered before photo-management work starts.

### Phase 3: Photo management on auto pages

**Status:** Done (pushed, CI green 2026-11-21)

**Objective:** Add, remove and reflow photos on auto pages without breaking the grid.

- [x] P3-W01: Extend `PageEditingService` with `auto_add(project_id, page_id, photo_id)`,
  `auto_reflow(project_id, page_id)` and `auto_remove_empty(project_id, page_id)`; add the
  matching routes. `auto_add` fills an empty slot when one exists and otherwise regenerates
  the snapshot with n+1 photos. `remove` stays unchanged and leaves a hole.
- [x] P3-W02: Add the generic drop zone to the layout panel for auto pages (including the
  zero-slot case), plus "Reflow" and "Remove empty slots" actions. Add a full-canvas drop
  zone overlay when the auto page has no slots.
- [x] P3-W03: Add service and `TestClient` tests for: add to an empty slot, add with no
  empty slot (re-flow), remove leaves the slot empty, reflow restores n slots, remove empty
  slots drops the holes.
- [x] P3-W04: Add a browser test that drops a photo on the auto drop zone and verifies the
  refreshed canvas and slot list.

**Acceptance criteria**

- Dragging a photo onto an auto page fills an empty slot or grows the layout.
- Removing a photo leaves the remaining cells exactly where they were.
- Reflow produces one slot per assigned photo.
- Crop, replace, swap and the keyboard crop flow keep working on auto pages.

**Phase gate:** Photo management is verified end-to-end before importance weighting.

### Phase 4: Image-analysis weighting

**Status:** Done (pushed, CI green 2026-11-21)

**Objective:** Bias cell areas toward photos with more relevant content.

- [x] P4-W01: Add an importance helper that runs `ObjectDetector` on a photo, maps
  detections to a score (`person`, `cat`, `dog`, `horse`, `cow`, `bird`) and applies
  `1 + min(score, cap) * layout.image_score_factor`. Cache results by image digest in
  memory; reuse the detector's existing disk cache. Return `1.0` when the detector or the
  model is unavailable.
- [x] P4-W02: Pass the per-photo importance into `build_auto_layout` and regenerate auto
  snapshots when the score factor or the model availability changes.
- [x] P4-W03: Add tests with a fake detector (no ONNX model required) proving that
  importance changes the allocation and that the fallback yields the plain layout.

**Acceptance criteria**

- With the model available, a high-scoring photo receives a larger cell than an otherwise
  identical low-scoring photo.
- Without a model, auto layout still works and is identical to importance `1.0`.
- No user-visible delay beyond the existing detector cache warm-up.

**Phase gate:** Weighting is optional and must never block rendering.

### Phase 5: Distribution and project settings

**Status:** Done (pushed, CI green 2026-11-21)

**Objective:** Integrate auto pages with distribution and output-profile changes.

- [x] P5-W01: Add `auto_target_slots` to the layout profile (default 6) and use it as the
  capacity of auto pages in `DistributionService`; generate the auto layout after applying
  a proposal.
- [x] P5-W02: Regenerate auto snapshots for a project when its output profile changes
  (page size, DPI, spacing, score factor) or when photos become available after a source
  rescan.
- [x] P5-W03: Expose `auto_target_slots` in the project settings form and configuration
  docs (run `make fmt` so `docs/usage/config.md` and `README.md` are regenerated).

**Acceptance criteria**

- Distribution fills auto pages up to the target and the resulting layout is a valid
  tiling.
- Changing the page size re-renders auto pages with the new canvas aspect.
- Documentation matches the typed defaults.

**Phase gate:** Auto pages behave like static pages in distribution and settings.

### Phase 6: Documentation, performance and acceptance

**Status:** Pending

**Objective:** Finish documentation, performance verification and end-to-end acceptance.

- [ ] P6-W01: Document the auto layout in `docs/usage/` (concept, behaviour, limits).
- [ ] P6-W02: Add a performance test that renders a project-sized set of auto pages and
  record the timings; optimise the candidate set if the budget is exceeded.
- [ ] P6-W03: Add the browser workflow test for the auto drop zone to
  `tests/test_browser_workflow.py` (Chromium; Firefox where practical).
- [ ] P6-W04: Run the full acceptance checklist from section 5 and close the plan.

**Acceptance criteria**

- `make fmt`, `make lint`, `make test` and the browser tests are green.
- A 53-page project with auto layouts can be created and exported within an acceptable
  time budget.
- No regressions in `tests/test_layouts.py`, `tests/test_page_rendering.py` or
  `tests/test_editing.py`.

**Phase gate:** Final phase; the plan is complete when the acceptance checklist passes.

## 5. Verification

Repository commands (see `Makefile`):

- Formatting and linting: `make fmt`, then `make lint`.
- Targeted tests:
  `uv run pytest tests/test_auto_layout.py tests/test_layouts.py tests/test_editing.py tests/test_gui.py -q`.
- Browser tests (skipped when browsers are missing):
  `uv run pytest tests/test_browser_workflow.py -m browser`.
- Full suite before a phase close: `make test`.
- After each push, monitor the GitHub Actions run for the pushed commit and require a
  definitive green result before closing the phase issue.

### Acceptance checklist

- [ ] Auto is the first entry in the project wizard and the per-page layout selector.
- [ ] 0–30 photos produce a full-bleed tiling with coverage `1.0` and no overlaps.
- [ ] One photo fills the canvas.
- [ ] Two photos split along the better axis for the canvas and photo orientation.
- [ ] One portrait plus two landscapes on a landscape canvas puts the portrait on one side
  and stacks the two landscapes next to it.
- [ ] Removing a photo leaves the grid unchanged; reflow restores n slots.
- [ ] Adding a photo fills an empty slot or grows the layout.
- [ ] Crop, replace, swap and keyboard crop work on auto pages.
- [ ] Preview caches invalidate after every auto layout change.
- [ ] No database schema change.
- [ ] `make fmt`, `make lint` and `make test` are green.

## 6. Dependencies, risks and open questions

### Dependencies and ordering

- Phase 2 depends on Phase 1.
- Phase 3 depends on Phase 2.
- Phase 4 can land after Phase 2 and before or after Phase 3; it only changes the layout
  input, not the management flow.
- Phase 5 depends on Phases 2 and 3.
- Phase 6 depends on all previous phases.

### Risks

- **Performance at project scale.** 0.2–0.4 s per 20–30-photo page adds up over 53 pages.
  Mitigation: cache photo metrics, generate layouts lazily or in the preview worker, and
  keep a cheaper candidate set for large n.
- **Snapshot growth.** Every regeneration inserts a new `auto` layout row. Mitigation:
  document the behaviour; add an optional cleanup that keeps only the snapshots referenced
  by pages.
- **Importance without a model.** Mitigation: fall back to `1.0` and never block rendering.
- **Preview thrash.** Rapid add/remove actions regenerate snapshots and invalidate previews.
  Mitigation: reuse the existing preview-worker coalescing and low-priority jobs.
- **Distribution mismatch.** Auto pages have zero slots until photos are assigned.
  Mitigation: `auto_target_slots` capacity plus post-distribution generation.
- **Order expectations.** Users may expect chronological order. The plan documents the
  orientation grouping and keeps the input order inside an orientation class; a future
  per-page toggle is out of scope.

### Resolved decisions

- Removal keeps the hole; reflow is explicit.
- Adding fills empty slots first, otherwise re-flows.
- YOLO importance is on by default with a fallback.
- Orientation grouping is allowed.
- Distribution uses a target slot count (default 6).

## Progress / Handoff

- **Mode:** autopilot
- **Plan:** `docs/plans/2026-11-21-auto-layout.md`
- **Completed:** P0 – prototype `/home/paul/.opencode/plan/auto_layout_proto.py`, review
  collages in `collages/` (FULL HD, 1–30 photos), exact-tiling and orientation checks;
  P1 – pure engine `layouts/auto_layout.py` + `tests/test_auto_layout.py` (162 tests, all
  green; coverage 1.0, no overlap, deterministic);
  P2 – `layout_choices()` with auto first, `PageEditingService` auto switch
  (`_plan_auto_change`, `_change_layout_auto`, `_auto_layout_for_page`), auto handling in
  project creation, `collage_aspect_for_page` helper, `LayoutRepository.next_version`,
  service + TestClient tests (`tests/test_auto_layout_integration.py`);
  P3 – `PageEditingService.auto_add` / `auto_reflow` / `auto_remove_empty` with snapshot
  reuse and hole placeholders, routes `POST .../auto/add|reflow|remove-empty`,
  layout-panel auto controls (Reflow, Remove empty slots, Add photo, dropzone),
  full-canvas dropzone when the auto page has no occupied slots, JS drop handling,
  CSS, service + TestClient tests and a Chromium/Firefox browser workflow test
  (`tests/test_browser_workflow.py::test_auto_layout_add_reflow_and_remove_empty`)
- **Active:** none (stopped after Phase 3 per user request)
- **Next:** P4-W01 `ObjectDetector` importance helper feeding `build_auto_layout`
  (reuse `layout.image_score_factor`, cache by image digest, fallback `1.0`)
- **Relevant files:**
  - `src/photo_composition_designer/layouts/loader.py` (catalogue, `LayoutTemplate`)
  - `src/photo_composition_designer/project/editing.py` (`PageEditingService` auto methods)
  - `src/photo_composition_designer/project/repositories.py` (`LayoutRepository`, `PageRepository.set_layout`)
  - `src/photo_composition_designer/project/rendering.py` (preview cache key)
  - `src/photo_composition_designer/project/distribution.py` (page capacity, apply)
  - `src/photo_composition_designer/gui/routes/editor.py` (auto add/reflow/remove-empty)
  - `src/photo_composition_designer/gui/routes/project_lifecycle.py` (project creation)
  - `src/photo_composition_designer/gui/routes/project_preview.py` (layout preview/apply)
  - `src/photo_composition_designer/gui/routes/project_context.py` (slots, overlays, catalogue)
  - `src/photo_composition_designer/gui/templates/partials/editor_canvas.html`
  - `src/photo_composition_designer/gui/static/editor.js`, `gui/static/style.css`
  - `src/photo_composition_designer/render/object_detector.py`, `render/smart_crop.py`
  - `src/photo_composition_designer/core/output_profile.py` (`LayoutProfile.image_score_factor`)
  - `tests/test_auto_layout_integration.py`, `tests/test_browser_workflow.py`,
    `tests/test_layouts.py`, `tests/test_editing.py`, `tests/test_gui.py`, `tests/test_page_rendering.py`
- **Decisions:**
  - Persisted snapshot with `key="auto"`, `version = max + 1`, slots `auto_0…auto_n-1`,
    assignments remapped by index.
  - Deterministic algorithm; no randomness.
  - Cost = area-weighted aspect distortion plus a one-sided area-fairness term.
  - Removal leaves a hole; `auto_add` fills the first empty slot, otherwise regenerates
    for n+1 while keeping hole placeholders so the grid does not move; explicit reflow
    and remove-empty rebuild one slot per assigned photo.
  - YOLO importance on by default with a `1.0` fallback; `image_score_factor` reused.
  - Orientation grouping allowed; input order kept inside a class.
  - Distribution target slot count default 6.
  - No database schema change.
- **Blockers:** none
- **Last verified:** 2026-11-21, Phase 3 pushed to `main` and CI green; `make lint` clean;
  `make test` 476 passed; targeted suites (`test_auto_layout.py`,
  `test_auto_layout_integration.py`, `test_layouts.py`, `test_page_rendering.py`,
  `test_editing.py`, `test_gui.py`) 289 passed; browser auto workflow passes in
  Chromium and Firefox
- **Context status:** clean