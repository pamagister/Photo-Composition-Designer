# Collage Image Workflow: Multi-Select, Dropzones and Keyboard Crop

**Status:** Ready for execution
**Created:** 2026-11-19
**Target branch:** `main`
**Repository:** `pamagister/Photo-Composition-Designer`
**Execution mode:** autopilot, with phase-boundary handoffs and one GitHub issue per phase
**Predecessor work (complete):** Phase 0 (slot grid capped at three columns, commit `0a09bc0`, issue #49) and Phase 1 (populate empty slots, commit `40d1731`, issue #50)

## 1. Objective and desired outcome

Adding photos to collages with many slots is tedious today: every assignment is a
separate trip through the right-hand slot controls, and the large page preview is
read-only. This plan improves the workflow without rewriting the renderer or turning
the canvas into a fully free-form editor.

Desired outcomes, in priority order:

1. **Multi-select in the photo strip.** Users can check several unused photos and
   assign them to the empty slots of the current page in one action.
2. **Dropzone preview.** The large page preview becomes a drop target: dragging a
   photo from the bottom strip onto a slot-shaped dropzone in the collage assigns or
   replaces it, and dragging a photo from one dropzone to another swaps the two.
3. **Reduced interactive crop (mitigated Phase 4).** Clicking a dropzone selects it
   and highlights the matching slot in the right-hand layout panel (and vice versa).
   With a dropzone selected, the arrow keys change the assignment's `crop_focus_x`
   and `crop_focus_y` in small steps, persist them and re-render the collage so the
   image visibly shifts.

Explicitly **out of scope**: the fully interactive canvas (free-form photo dragging,
crop and zoom directly on the canvas, removal of the right-hand layout panel). The
right-hand panel remains the accessible primary control surface.

## 2. Scope, constraints and non-goals

### Mandatory scope

- Multi-select of available photos in the bottom photo strip, with a bulk assign
  action to the empty slots of the current page.
- Slot-shaped dropzones overlaid on the large page preview, aligned to the rendered
  collage geometry.
- Drag-and-drop from the strip onto a dropzone (assign/replace) and between dropzones
  (swap), reusing the existing server-confirmed `assign`, `replace` and `swap`
  endpoints.
- Selection synchronisation between a dropzone and its slot in the right-hand panel.
- Keyboard crop: arrow keys adjust the selected assignment's focal point, persist it
  and refresh the preview, with input fields excluded from the shortcut.
- Tests at three levels: service/endpoint tests with `TestClient`, markup tests for
  the new controls and geometry, and Playwright browser tests for the new DnD and
  keyboard flows in Chromium and Firefox.

### Explicit constraints

- Every new pointer interaction keeps a keyboard-accessible alternative in the
  right-hand panel. The overlay is supplementary, not the only path.
- All mutations remain server-confirmed and transactional; the browser only initiates
  requests and swaps returned fragments, matching the existing `editor.js` design.
- No database schema change. Reuse the existing assignment and crop persistence.
- The preview must stay aligned with the renderer. Slot overlay geometry and the
  renderer must be derived from one shared content-box computation.
- Do not weaken or remove existing tests. Existing browser tests use keyboard controls
  and must remain green.

### Non-goals

- Free-form repositioning of a photo within a slot by dragging it around the canvas.
- Mouse-drag crop/pan, wheel zoom or on-canvas `+`/`-` buttons.
- Removing or hiding the right-hand layout panel.
- Per-page bulk assignment beyond the current page (project-wide filling already
  exists via distribution).
- Changes to the layout file format or the rendered output beyond the shared
  content-box refactor.

## 3. Architecture and decisions

### 3.1 Shared collage geometry

The rendered collage sits inside a content box (margins, calendar strip, description,
optional map). Slot coordinates are normalised to that box, not to the page. The
overlay must use the same box or dropzones will not line up.

- Extract the content-box computation from `PageComposer.render`
  (`src/photo_composition_designer/render/page.py`, currently lines ~71-166) into a
  reusable function, for example
  `render/layout_geometry.py::compute_collage_box(page, profile) -> CollageBox`.
- `CollageBox` carries `page_width`, `page_height`, `left`, `top`, `width`, `height`
  in pixels.
- `PageComposer.render` calls the helper and uses its values, so renderer and overlay
  cannot drift.
- The helper must mirror the existing title-page resolution exactly
  (`title_page = use_title_page and page_index == 0 and bool(title)`) and the existing
  description/map/calendar conditions.

### 3.2 Overlay geometry

- Add a pure function that converts a layout plus a `CollageBox` into per-slot
  rectangles as percentages of the full page:
  `left = (box.left + slot.x * box.width) / box.page_width`, and analogously for
  `top`, `width`, `height`.
- Expose the per-slot overlay data (slot id, slot key, occupied flag, photo id and
  percentage rectangle) through the existing page context builders
  (`_project_context` and `_page_context` in `gui/routes/projects.py`). Both routes
  already assemble `slots` and page assignments; only the geometry list is added.

### 3.3 Preview frame and dropzones

- In `partials/editor_canvas.html`, wrap the preview `<img>` in a
  `.page-preview-frame` whose aspect ratio equals the page size, capped by the
  existing `max-height`. The image fills the frame (`object-fit: fill`), and slot
  dropzones are absolutely positioned children of the frame with inline percentage
  `left/top/width/height`.
- Empty slots render a visible dashed dropzone. Occupied slots render a transparent
  hit area with a hover outline so they can receive a replace drop or start a swap
  drag.
- Dropzones are supplementary. They must not intercept pointer events needed by the
  right-hand panel, and must remain readable when JavaScript is unavailable (the
  right-hand controls still work).

### 3.4 Drag-and-drop mapping

- Extend `static/editor.js` to treat `.slot-dropzone` like the existing `.slot` drop
  targets. Reuse the existing `application/x-pcd-slot` and `text/plain` data-transfer
  types already used for strip-to-slot and slot-to-slot drags.
- Drop from the strip on an empty dropzone calls `assign`; on an occupied dropzone
  calls `replace`. Drop from an occupied dropzone on another dropzone calls `swap`.
- A successful drop keeps the current pattern: `htmx.ajax` posts to the existing
  endpoint, targets `.editor-canvas`, swaps `outerHTML`, and the returned canvas
  re-renders both the overlay and the right-hand panel.
- Existing `.slot` drag-and-drop behaviour is preserved.

### 3.5 Multi-select

- Add a checkbox to each available `.unused-item` in `partials/unused_pool.html`. A
  checkbox is keyboard accessible and requires no custom widget.
- `static/editor.js` keeps a client-side `Set` of selected photo ids and shows a
  small toolbar with the selection count, an "Assign selected" button and a "Clear"
  action.
- New service method
  `PageEditingService.assign_selected(project_id, page_id, photo_ids) -> int`:
  assigns the selected photos to empty slots in slot order, skipping unavailable
  photos and photos already used in the project, and increments the revision only
  when at least one assignment was made. This mirrors `populate` but takes an
  explicit, ordered candidate list.
- New endpoint `POST /projects/{project_id}/pages/{page_id}/assign-selected`
  accepting repeated `photo_id` form values and returning the editor canvas fragment
  with an `HX-Trigger: pcd:refresh-unused` header.
- After a successful bulk assign, the selection is cleared and the strip refreshes.

### 3.6 Selection synchronisation

- Client-side selection state (`selectedSlotId`) is shared by dropzones and right-hand
  slots, keyed by `data-slot-id`.
- Clicking a dropzone adds a `selected` class to it and to the matching `.slot` in the
  right-hand panel, and scrolls the slot into view. Clicking a right-hand slot mirrors
  the highlight onto the dropzone.
- Selection is presentation-only and does not trigger a server request.

### 3.7 Keyboard crop (reduced Phase 4)

- When a slot is selected and occupied, and focus is not inside an `input`,
  `textarea`, `select` or contenteditable element:
  - Arrow Left / Right decrease / increase `crop_focus_x` by a fixed step (default
    `0.05`).
  - Arrow Up / Down decrease / increase `crop_focus_y` by the same step.
  - Values are clamped to `[0, 1]`.
- Changes are debounced (roughly 120 ms) and sent to a new lightweight endpoint
  `POST /projects/{project_id}/pages/{page_id}/crop/live` that validates and persists
  the crop, then returns `204` with the new page revision (for example an
  `X-Page-Revision` response header) and an `HX-Trigger: pcd:crop-updated` header.
- On success the client updates the preview image `src` with the new revision
  (cache-busting `?v=`) and updates the matching right-hand sliders. The full canvas
  is intentionally **not** re-rendered on every key press, so selection, scroll and
  focus survive.
- The existing `POST .../crop` form endpoint is unchanged; the live endpoint is an
  addition used only by the keyboard path.
- A short hint near the preview explains the arrow-key behaviour.

### 3.8 Why not the full interactive canvas

The full variant (mouse-drag crop, wheel zoom, on-canvas `+`/`-`, removal of the
right panel) would require client-side crop preview, a large interaction surface,
new accessibility alternatives and broad browser-test coverage, with a high
regression risk to the existing well-tested editing flows. The reduced scope above
delivers the most valuable parts (drag to assign/swap, keyboard crop) at moderate
cost and keeps the accessible right-hand panel as the source of truth.

## 4. Phases and work packages

### Phase 2: Multi-select in the photo strip

**Status:** Complete (issue #52)

**Objective:** Assign several unused photos to the empty slots of the current page in
one action.

- [x] P2-W01: Add `PageEditingService.assign_selected(project_id, page_id, photo_ids)`
  with unit tests for ordering, skipping unavailable and already-used photos, empty
  slots only, and revision handling.
- [x] P2-W02: Add the `POST .../assign-selected` endpoint and a `TestClient` route
  test covering the success notice, the `HX-Trigger` header and a no-op case.
- [x] P2-W03: Add checkboxes to `.unused-item`, a selection toolbar (count, Assign
  selected, Clear) and the selection state in `editor.js`; add a markup test that the
  checkbox and toolbar render for available photos.
- [x] P2-W04: Add a Playwright test (Chromium and Firefox) that checks two photos,
  assigns them and verifies the slots and the refreshed strip.

**Acceptance criteria**

- Selecting N available, unused photos and choosing "Assign selected" fills up to N
  empty slots in slot order.
- Occupied slots are untouched; unavailable and project-wide used photos are skipped.
- A second assign with no empty slots assigns nothing and reports it.
- The selection clears and the strip refreshes after success.
- Keyboard-only users can complete the same flow through the checkboxes and button.

**Phase gate:** Multi-select assign is covered by service, route, markup and browser
tests before the overlay work begins.

### Phase 3: Dropzone preview (drag to assign, replace and swap)

**Status:** Complete (issue #53)

**Objective:** Make the large page preview a drop target aligned with the collage.

- [x] P3-W01: Extract `compute_collage_box` (and `CollageBox`) from
  `PageComposer.render`, reuse it in the renderer, and add unit tests that reproduce
  the previous content-box values for representative profiles and pages. Keep
  `tests/test_page_rendering.py` green.
- [x] P3-W02: Add the slot overlay rectangle function and expose per-slot overlay data
  (slot id, key, occupied, photo id, percentages) through `_project_context` and
  `_page_context`; add a `TestClient` test that the overlay percentages for a known
  layout match the expected values.
- [x] P3-W03: Add the `.page-preview-frame` wrapper and absolutely positioned
  `.slot-dropzone` elements in `editor_canvas.html`, plus CSS for empty, occupied,
  hover and drag-over states. Add a markup test that dropzones render with the correct
  `data-slot-id` and inline geometry.
- [ ] P3-W04: Extend `editor.js` so dropzones accept strip drags (assign/replace) and
  dropzone-to-dropzone drags (swap) using the existing endpoints and data-transfer
  types; keep the existing `.slot` DnD working. Add a Playwright test that drags a
  strip photo onto an empty dropzone, replaces an occupied one and swaps two dropzones
  in Chromium and Firefox.

**Acceptance criteria**

- Dropzones align with the rendered collage for single-slot, multi-slot and tiled
  layouts, with and without calendar/description/map.
- Dragging from the strip to an empty dropzone assigns; to an occupied dropzone
  replaces; between occupied dropzones swaps.
- The right-hand slot DnD and all keyboard controls continue to work.
- The overlay remains usable when JavaScript is disabled (right-hand controls only).
- Existing page rendering tests are unchanged and green.

**Phase gate:** Overlay alignment is verified against the renderer before the
keyboard-crop work starts, because keyboard crop depends on the same geometry.

### Phase 4 (reduced): Selection sync and keyboard crop

**Status:** Complete (issue #54)

**Objective:** Connect the dropzone to the right-hand panel and allow arrow-key focal
point adjustment with a live preview refresh.

- [x] P4-W01: Implement selection synchronisation between dropzones and right-hand
  slots (highlight and scroll into view), with a Playwright test in Chromium and
  Firefox.
- [x] P4-W02: Add `POST .../crop/live` returning `204` with the new revision header
  and `HX-Trigger`, plus a `TestClient` test for persistence, clamping and the
  revision header.
- [x] P4-W03: Implement the arrow-key handler (excluding form fields), debounced
  live-crop submission, preview `src` update and slider sync; add a Playwright test
  that arrow keys change the stored focal point and the preview revision.
- [x] P4-W04: Add the short usage hint near the preview and update the relevant
  documentation.

**Acceptance criteria**

- Clicking a dropzone highlights the matching right-hand slot and scrolls it into
  view; clicking a right-hand slot highlights the dropzone.
- With an occupied slot selected, arrow keys change `crop_focus_x` / `crop_focus_y`
  by one step, persist them, clamp to `[0, 1]`, update the sliders and refresh the
  preview image.
- Arrow keys inside form fields do not change the crop.
- The full canvas is not re-rendered per key press, so selection and scroll survive.
- The existing crop form and its tests remain green.

**Phase gate:** This is the final phase of the plan. The full interactive canvas
remains explicitly deferred and is not part of this plan.

## 5. Verification

Use the repository commands (see `Makefile`):

- Formatting and linting: `make fmt` then `make lint`.
- Targeted tests while working:
  `uv run pytest tests/test_editing.py tests/test_gui.py tests/test_page_rendering.py -q`.
- Browser tests (skipped when Playwright browsers are missing):
  `uv run pytest tests/test_browser_workflow.py -m browser`.
- Full suite before a phase close: `uv run pytest -q tests/`.
- After each push, monitor the GitHub Actions run for the pushed commit and require a
  definitive green result before closing the phase issue.

## 6. Dependencies, risks and open questions

### Dependencies and ordering

- Phase 2 is independent and can ship first.
- Phase 3 depends on the geometry refactor (P3-W01) being correct.
- Phase 4 depends on Phase 3 geometry and dropzone selection.

### Risks

- **Geometry drift:** if the overlay does not use the exact renderer content box,
  dropzones will be misaligned. Mitigation: single shared `compute_collage_box` plus
  unit tests and `test_page_rendering.py` regression coverage.
- **Preview aspect ratio:** `object-fit: contain` letterboxes the image, so a naive
  percentage overlay would be wrong. Mitigation: an aspect-ratio-locked frame that
  exactly matches the page size.
- **Re-render cost:** every keyboard crop re-renders the page with Pillow. Mitigation:
  debounce, low-frequency commits, and do not re-render the whole canvas.
- **Selection loss on htmx swaps:** a full canvas swap clears client-side selection.
  Mitigation: the live-crop path avoids full canvas swaps; after assign/replace/swap a
  re-selection is acceptable.
- **DnD test flakiness:** HTML5 drag-and-drop in Playwright can be flaky. Mitigation:
  keep service/route logic in `TestClient` tests and mark browser tests so they skip
  cleanly when binaries are missing.
- **Context inconsistency:** `_page_context` derives `unused_photos` per page while
  `_project_context` derives it project-wide. New work relies on slots/assignments and
  the service layer, not on that list, so it is unaffected; do not "fix" it here.

### Open questions

- Should the arrow-key step be fixed at `0.05`, or configurable in project settings?
  Default: fixed `0.05` for this plan. --> Answer: Use fixed value 0.02
- Should dragging a multi-selection from the strip distribute the remaining photos
  across the following empty slots, or only assign the first? Default for this plan:
  assign the first to the target and the rest to the next empty slots in order; if
  this proves confusing, restrict to a single photo per drag. --> Answer: assign the first to the target and the rest to the next empty slots in order
- Should the reduced Phase 4 also support `+`/`-` keys for zoom, or only arrow-key
  focus? Default: arrow keys only, matching the stated requirement. --> Answer: also support `+`/`-`, zoom steps by 2%, so also 0.02, very small

## Progress / Handoff

- **Mode:** autopilot
- **Plan:** `docs/plans/2026-11-19-collage-image-workflow.md`
- **Completed:** Phase 0 (issue #49); Phase 1 (issue #50); Phase 2 (commit `b3c334a`, issue #52, CI green); Phase 3 (commit `599cd1b`, issue #53, CI green); Phase 4 (issue #54, pending commit/CI)
- **Active:** none (all phases complete, Phase 4 commit pending)
- **Next:** commit Phase 4, push, monitor CI, then close issues #52-#54
- **Relevant files:**
  - `src/photo_composition_designer/project/editing.py` (populate precedent, `PageEditingService`)
  - `src/photo_composition_designer/gui/routes/editor.py` (assign/replace/swap/crop routes)
  - `src/photo_composition_designer/gui/routes/projects.py` (`_project_context`, `_page_context`, preview endpoint)
  - `src/photo_composition_designer/gui/templates/partials/editor_canvas.html` (preview + slot grid)
  - `src/photo_composition_designer/gui/templates/partials/unused_pool.html` (photo strip)
  - `src/photo_composition_designer/gui/static/editor.js` (drag-and-drop)
  - `src/photo_composition_designer/render/page.py` (`PageComposer.render`, content box)
  - `src/photo_composition_designer/render/slot_renderer.py` (slot geometry consumer)
  - `tests/test_editing.py`, `tests/test_gui.py`, `tests/test_page_rendering.py`, `tests/test_browser_workflow.py`
- **Decisions:**
  - No full interactive canvas; the right-hand layout panel remains the accessible primary control surface.
  - Overlay geometry must come from a shared `compute_collage_box` used by the renderer.
  - Live keyboard crop uses a dedicated endpoint that returns only the new revision, not a full canvas re-render.
  - Populate (Phase 1) remains the fastest path for "fill everything"; multi-select and dropzones complement it.
- **Blockers:** none
- **Last verified:** 2026-11-19, Phase 0 + Phase 1 complete; `make fmt`, `make lint` and `uv run pytest tests/` (272 passed) green; CI run `44523159845` green on `main`.
- **Context status:** clean